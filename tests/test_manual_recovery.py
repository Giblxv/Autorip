import os
from pathlib import Path

import pytest
from autorip import server
from autorip.paths import write_archive_marker
from autorip.prt import read_header


@pytest.fixture
def paused_app(app_home, monkeypatch):
    # Simula queda antes de o worker retirar o upload da fila.
    with monkeypatch.context() as scoped:
        scoped.setattr(server.threading.Thread, "start", lambda self: None)
        yield server.App()


def upload(app, sample_png, width):
    raw = sample_png.read_bytes()
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        def _save_request_body(self, path, maximum):
            Path(path).write_bytes(raw)
    app.receive_upload(Handler(), "manual.png", str(width) if width is not None else "")
    return app.q.get_nowait()


@pytest.mark.parametrize("width", [2.54, None])
def test_reinicio_preserva_largura_e_dimensoes_do_prt(paused_app, sample_png, monkeypatch, width):
    original, source, _, _ = upload(paused_app, sample_png, width)
    resumed = server.App()
    job = resumed._enqueue_manual_recovery(source)
    assert resumed.q.get_nowait()[2] == width
    # Executa o worker real e confere a escala do arquivo publicado.
    resumed.q.put((job, source, width, True))
    # O worker é executado de forma síncrona por uma única passagem da fila.
    original_get = resumed.q.get
    calls = []
    def one_job():
        if calls:
            raise KeyboardInterrupt
        calls.append(True)
        return original_get()
    monkeypatch.setattr(resumed.q, "get", one_job)
    with pytest.raises(KeyboardInterrupt):
        resumed._worker()
    assert job["status"] == "pronto"
    expected = round((width or (300/300*2.54)) / 2.54 * 300)
    assert read_header(job["out"])["n_dots"] == expected
    assert not Path(source + ".request.json").exists()


def test_parametros_corrompidos_preservam_imagem_sem_reprocessar(paused_app, sample_png):
    _, source, _, _ = upload(paused_app, sample_png, 20)
    Path(source + ".request.json").write_text('{"width_cm": 99}')
    assert paused_app._enqueue_manual_recovery(source) is None
    assert os.path.isfile(source)
    assert paused_app.q.empty()


def test_interrupcao_durante_rip_preserva_largura(paused_app, sample_png):
    _, source, _, _ = upload(paused_app, sample_png, 20)
    write_archive_marker(source, {"phase":"processing", "target":"done",
                                "source_signature":list(server._signature(source))})
    resumed = server.App()
    assert resumed._recover_marked_source(source, resumed.s) is False
    resumed._enqueue_manual_recovery(source)
    assert resumed.q.get_nowait()[2] == 20


def test_falha_na_persistencia_nao_confirma_upload(paused_app, sample_png, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disco indisponivel")
    monkeypatch.setattr(server, "write_json_atomic", fail)
    with pytest.raises(OSError):
        upload(paused_app, sample_png, 20)
    assert not list(Path(paused_app.inbox).iterdir())
    assert paused_app.q.empty()


def test_imagem_alterada_nao_recebe_parametros_de_outra_entrada(paused_app, sample_png):
    _, source, _, _ = upload(paused_app, sample_png, 20)
    with open(source, 'ab') as target:
        target.write(b'alterada')
    assert paused_app._enqueue_manual_recovery(source) is None
    assert paused_app.q.empty()
    assert Path(source).exists()


def test_limpeza_de_sidecar_re_tenta_bloqueio_temporario(paused_app, sample_png, monkeypatch):
    _, source, _, _ = upload(paused_app, sample_png, 20)
    sidecar = source + '.request.json'
    os.remove(source)
    original_remove = server.os.remove
    attempts = []
    def remove(path):
        if path == sidecar and not attempts:
            attempts.append(True)
            raise PermissionError('antivirus')
        return original_remove(path)
    monkeypatch.setattr(server.os, 'remove', remove)
    paused_app._cleanup_manual_folder(source)
    assert attempts and not Path(source).parent.exists()
