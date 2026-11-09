"""Admissão antes de I/O: largura, capacidade, reservas e uploads lentos."""
import json
from pathlib import Path
import shutil
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

from autorip import server
from autorip.paths import write_json_atomic
from autorip.paths import write_archive_marker
from autorip.prt import PrtWriter


@pytest.fixture
def idle_app(app_home):
    class IdleApp(server.App):
        def _worker(self):
            pass

        def _watch(self):
            pass

    return IdleApp()


def hot_file(app, sample_png):
    path = Path(app.s.hot_folder) / 'manual.png'
    shutil.copyfile(sample_png, path)
    return path


def fill(app, monkeypatch):
    monkeypatch.setattr(server, 'MAX_PENDING_JOBS', 1)
    return app.enqueue(str(Path(app.processing_folder) / 'busy.png'))


class Handler:
    def __init__(self, raw):
        self.raw = raw
        self.headers = {'Content-Length': str(len(raw))}
        self.reads = 0

    def _save_request_body(self, path, maximum):
        self.reads += 1
        Path(path).write_bytes(self.raw)


@pytest.mark.parametrize('width', ['nan', '0', '-1', '301', 'abc', True])
def test_invalid_hot_width_does_not_move_art(idle_app, sample_png, width):
    path = hot_file(idle_app, sample_png)
    with pytest.raises(ValueError):
        idle_app.enqueue_hot_file(path.name, width)
    assert path.read_bytes() == sample_png.read_bytes()
    assert not list(Path(idle_app.processing_folder).iterdir())
    assert not idle_app.queued_sources


def test_full_hot_admission_keeps_art_in_original_folder(idle_app, sample_png, monkeypatch):
    fill(idle_app, monkeypatch)
    path = hot_file(idle_app, sample_png)
    with pytest.raises(RuntimeError, match='Fila cheia'):
        idle_app.enqueue_hot_file(path.name, '2.54')
    assert path.read_bytes() == sample_png.read_bytes()
    assert not list(Path(idle_app.processing_folder).iterdir())


def test_full_upload_is_rejected_before_receiving_body(idle_app, sample_png, monkeypatch):
    fill(idle_app, monkeypatch)
    handler = Handler(sample_png.read_bytes())
    with pytest.raises(RuntimeError, match='Fila cheia'):
        idle_app.receive_upload(handler, 'art.png', '2.54')
    assert handler.reads == 0
    assert not list(Path(idle_app.inbox).iterdir())


def test_invalid_upload_width_is_rejected_before_body(idle_app, sample_png):
    handler = Handler(sample_png.read_bytes())
    with pytest.raises(ValueError):
        idle_app.receive_upload(handler, 'art.png', 'nan')
    assert handler.reads == 0
    assert not list(Path(idle_app.inbox).iterdir())


def test_reservation_blocks_competing_admission_and_converts_once(idle_app, monkeypatch):
    monkeypatch.setattr(server, 'MAX_PENDING_JOBS', 1)
    with idle_app._reserve_admission() as token:
        with pytest.raises(RuntimeError, match='Fila cheia'):
            idle_app.enqueue(str(Path(idle_app.processing_folder) / 'other.png'))
        job = idle_app.enqueue(str(Path(idle_app.processing_folder) / 'reserved.png'), _reservation=token)
        assert job['status'] == 'fila'
        assert not idle_app._admission_reservations
        with pytest.raises(RuntimeError):
            idle_app.enqueue(str(Path(idle_app.processing_folder) / 'reused.png'), _reservation=token)
    assert len(idle_app.queued_sources) == 1 and idle_app.q.qsize() == 1


def test_move_failure_releases_reservation_without_moving_art(idle_app, sample_png, monkeypatch):
    path = hot_file(idle_app, sample_png)
    def fail(*args):
        raise PermissionError('test move denied')
    monkeypatch.setattr(server, 'move_unique', fail)
    with pytest.raises(PermissionError):
        idle_app.enqueue_hot_file(path.name, '2.54')
    assert path.is_file() and not idle_app._admission_reservations
    assert not idle_app.queued_sources


@pytest.mark.parametrize('failure', ['body', 'image', 'sidecar'])
def test_failed_upload_releases_slot_and_removes_partial_files(idle_app, sample_png, monkeypatch, failure):
    handler = Handler(b'not an image' if failure == 'image' else sample_png.read_bytes())
    def fail(*args, **kwargs):
        raise OSError('test I/O failure')
    if failure == 'body':
        handler._save_request_body = fail
    elif failure == 'sidecar':
        monkeypatch.setattr(server, 'write_json_atomic', fail)
    with pytest.raises(OSError):
        idle_app.receive_upload(handler, 'failed.png', '2.54')
    assert not idle_app._admission_reservations and not idle_app.queued_sources
    assert not list(Path(idle_app.inbox).iterdir())


def test_slow_upload_does_not_block_hot_folder_scan(idle_app, sample_png, monkeypatch):
    monkeypatch.setattr(server, 'MAX_PENDING_JOBS', 2)
    raw = sample_png.read_bytes()
    entered, release = threading.Event(), threading.Event()
    errors, jobs = [], []
    class SlowHandler(Handler):
        def _save_request_body(self, path, maximum):
            Path(path).write_bytes(raw[:16])
            entered.set()
            if not release.wait(10):
                raise TimeoutError('test did not release upload')
            Path(path).write_bytes(raw)
    def upload():
        try:
            jobs.append(idle_app.receive_upload(SlowHandler(raw), 'slow.png', '2.54'))
        except BaseException as error:
            errors.append(error)
    thread = threading.Thread(target=upload, daemon=True)
    thread.start()
    try:
        assert entered.wait(5)
        available = idle_app.upload_lock.acquire(timeout=1)
        if available:
            idle_app.upload_lock.release()
        assert available, 'Upload bloqueou o lock usado pelo observador'
        assert len(idle_app._admission_reservations) == 1
        hot_file(idle_app, sample_png)
        idle_app.auto = True
        idle_app._scan_inputs()
        assert len(idle_app.queued_sources) == 1
        assert idle_app.jobs[0]['name'] == 'manual.png'
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive() and not errors
    assert len(jobs) == 1 and len(idle_app.queued_sources) == 2
    assert not idle_app._admission_reservations
    assert idle_app.job_controls[jobs[0]['id']]['item'][2] == 2.54


def test_full_scan_preserves_hot_inputs_without_warning_spam(idle_app, sample_png, monkeypatch):
    fill(idle_app, monkeypatch)
    path = hot_file(idle_app, sample_png)
    idle_app.auto = True
    before = list(idle_app.log_lines)
    idle_app._scan_inputs()
    idle_app._scan_inputs()
    assert path.is_file() and not list(Path(idle_app.processing_folder).iterdir())
    assert idle_app.log_lines == before


def test_manual_recovery_waits_for_capacity_without_losing_width(idle_app, sample_png, monkeypatch):
    busy = fill(idle_app, monkeypatch)
    folder = Path(idle_app.inbox) / 'pending'
    folder.mkdir()
    path = folder / 'pending.png'
    shutil.copyfile(sample_png, path)
    write_json_atomic(str(path) + '.request.json', {'version': 1, 'width_cm': 2.54, 'sha256': server.file_sha256(path)})
    idle_app._scan_inputs()
    assert path.is_file() and len(idle_app.jobs) == 1
    busy_path = idle_app.job_controls[busy['id']]['item'][1]
    idle_app._release_source(busy_path)
    idle_app._scan_inputs()
    assert len(idle_app.queued_sources) == 1
    control = idle_app.job_controls[idle_app.jobs[-1]['id']]
    assert control['item'][2] == 2.54


def test_http_full_upload_returns_429(idle_app, sample_png, monkeypatch):
    fill(idle_app, monkeypatch)
    idle_app.tokens.add('admission-test')
    monkeypatch.setattr(server, 'APP', idle_app)
    with ThreadingHTTPServer(('127.0.0.1', 0), server.H) as http:
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f'http://127.0.0.1:{http.server_port}/api/upload?name=test.png',
                              data=sample_png.read_bytes(), headers={'X-Token': 'admission-test'})
            with pytest.raises(HTTPError) as failure:
                urlopen(request, timeout=10)
            assert failure.value.code == 429
            assert 'Fila cheia' in json.load(failure.value)['error']
        finally:
            http.shutdown()
            thread.join(timeout=2)


def test_full_queue_still_finishes_recovery_of_published_prt(idle_app, sample_png, monkeypatch):
    fill(idle_app, monkeypatch)
    path = Path(idle_app.processing_folder) / 'recovery.png'
    shutil.copyfile(sample_png, path)
    output = Path(idle_app.s.output_folder) / 'recovery.PRT'
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    write_archive_marker(str(path), {'phase': 'success', 'target': 'done', 'output': output.name,
        'output_dir': idle_app.s.output_folder, 'output_sha256': server.file_sha256(output),
        'source_signature': list(server._signature(path)), 'metadata_written': False, 'outbox_handled': True,
        'info': {'width_cm': 8 / 300 * 2.54, 'height_cm': 1 / 300 * 2.54,
                 'n_rows': 1, 'n_dots': 8, 'dpi_x': 300, 'dpi_y': 300, 'has_alpha': True}})
    idle_app._scan_inputs()
    assert (Path(idle_app.s.done_folder) / path.name).is_file()
    assert Path(str(output) + '.meta.json').is_file()
    assert len(idle_app.queued_sources) == 1 and idle_app.q.qsize() == 1


def test_reserved_upload_prevents_idle_shutdown(idle_app):
    assert server._can_close_idle_browser(idle_app)
    with idle_app._reserve_admission():
        assert not server._can_close_idle_browser(idle_app)
    assert server._can_close_idle_browser(idle_app)


def test_insufficient_disk_releases_slot_before_body(idle_app, sample_png, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(server, 'shutil', SimpleNamespace(disk_usage=lambda _: SimpleNamespace(free=0)))
    handler = Handler(sample_png.read_bytes())
    with pytest.raises(server.InsufficientStorageError):
        idle_app.receive_upload(handler, 'art.png', '2.54')
    assert handler.reads == 0 and not idle_app._admission_reservations
    assert not list(Path(idle_app.inbox).iterdir())


def test_failed_publication_hides_image_before_unlocking_recovery(idle_app, sample_png, monkeypatch):
    class PublicationLock:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            assert not list(Path(idle_app.inbox).rglob('*.png')), 'Recuperação viu imagem de pedido recusado'
    def fail(*args, **kwargs):
        raise OSError('admission failed')
    idle_app.upload_lock = PublicationLock()
    monkeypatch.setattr(idle_app, 'enqueue', fail)
    with pytest.raises(OSError, match='admission failed'):
        idle_app.receive_upload(Handler(sample_png.read_bytes()), 'art.png', '2.54')
    assert not idle_app._admission_reservations and not list(Path(idle_app.inbox).iterdir())
