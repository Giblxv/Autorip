from pathlib import Path
from types import SimpleNamespace
import json
import os
import stat
import threading

import pytest

from autorip import server
from autorip.paths import safe_filename
from autorip.watcher import EXTS
from test_server import panel, request


def listing_app(folder):
    app = server.App.__new__(server.App)
    app.s = SimpleNamespace(hot_folder=str(folder))
    app.settings_lock = threading.RLock()
    app._hot_listing_lock = threading.Lock()
    return app


def patch_scandir(monkeypatch, folder, factory):
    original = server.os.scandir
    target = os.path.normcase(os.path.realpath(folder))
    def scoped(path):
        try:
            selected = os.path.normcase(os.path.realpath(path)) == target
        except (TypeError, OSError):
            selected = False
        return factory() if selected else original(path)
    monkeypatch.setattr(server.os, 'scandir', scoped)


def reference_listing(folder):
    result = []
    for name in sorted(os.listdir(folder), key=str.casefold):
        if name.startswith('.') or not name.lower().endswith(EXTS):
            continue
        path = os.path.join(folder, name)
        info = os.lstat(path)
        if stat.S_ISREG(info.st_mode) and not os.path.islink(path):
            result.append(dict(name=safe_filename(name), size=info.st_size, mtime=info.st_mtime))
    return result


def test_listing_preserves_filters_sorting_sanitization_and_exact_metadata(tmp_path):
    names = ['z.PNG', 'Arte.jpeg', 'a.PNG', 'área.TIFF', '中.tif', 'B.jpg',
             '.hidden.png', 'ignored.txt', 'incomplete.png.part', ' long name .png']
    if os.name != 'nt':
        names += ['A.png', 'bad:name.png']
    for index, name in enumerate(names):
        path = tmp_path / name
        path.write_bytes(b'x' * index)
        os.utime(path, ns=(1700000000000000000 + index * 1234567,) * 2)
    (tmp_path / 'directory.png').mkdir()
    actual = listing_app(tmp_path).list_hot_files()
    expected = reference_listing(tmp_path)
    assert actual == expected
    assert json.dumps(actual, separators=(',', ':')) == json.dumps(expected, separators=(',', ':'))
    assert all(set(row) == {'name', 'size', 'mtime'} for row in actual)


def test_listing_excludes_file_links_and_broken_links(tmp_path):
    source = tmp_path / 'real.png'
    source.write_bytes(b'art')
    try:
        (tmp_path / 'alias.png').symlink_to(source)
        (tmp_path / 'missing.png').symlink_to(tmp_path / 'missing-target')
    except OSError:
        pytest.skip('links indisponiveis neste ambiente')
    assert listing_app(tmp_path).list_hot_files() == reference_listing(tmp_path)
    assert [row['name'] for row in listing_app(tmp_path).list_hot_files()] == ['real.png']


@pytest.mark.parametrize('kind', ['missing', 'not_directory'])
def test_missing_or_invalid_folder_remains_empty(tmp_path, kind):
    path = tmp_path / 'unavailable'
    if kind == 'not_directory':
        path.write_bytes(b'file')
    assert listing_app(path).list_hot_files() == []


def test_each_scan_observes_replacement_size_and_current_folder(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir(); second.mkdir()
    source = first / 'art.png'; source.write_bytes(b'old')
    app = listing_app(first)
    assert app.list_hot_files()[0]['size'] == 3
    temporary = first / '.incoming'; temporary.write_bytes(b'new-content')
    os.replace(temporary, source)
    assert app.list_hot_files() == reference_listing(first)
    source.unlink()
    assert app.list_hot_files() == []
    (second / 'other.TIF').write_bytes(b'other')
    app.s.hot_folder = str(second)
    assert app.list_hot_files() == reference_listing(second)


def test_scan_closes_and_ignores_entries_that_disappear(tmp_path, monkeypatch):
    calls = []
    class Entry:
        def __init__(self, name, missing=False):
            self.name, self.missing = name, missing
        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            calls.append(self.name)
            if self.missing:
                raise FileNotFoundError(self.name)
            return SimpleNamespace(st_mode=stat.S_IFREG, st_size=7, st_mtime=123.5)
    class Entries:
        closed = False
        def __enter__(self):
            return iter([Entry('Z.png'), Entry('gone.png', True), Entry('.hidden.png'), Entry('ignored.txt'), Entry('a.png')])
        def __exit__(self, *args):
            self.closed = True
    entries = Entries()
    patch_scandir(monkeypatch, tmp_path, lambda: entries)
    assert listing_app(tmp_path).list_hot_files() == [dict(name='a.png', size=7, mtime=123.5), dict(name='Z.png', size=7, mtime=123.5)]
    assert entries.closed and calls == ['Z.png', 'gone.png', 'a.png']


def test_failed_enumeration_does_not_return_a_partial_snapshot(tmp_path, monkeypatch):
    class Entries:
        closed = False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.closed = True
        def __iter__(self):
            raise PermissionError('indisponivel')
    entries = Entries()
    patch_scandir(monkeypatch, tmp_path, lambda: entries)
    assert listing_app(tmp_path).list_hot_files() == [] and entries.closed


def test_http_etag_updates_after_file_changes_and_still_requires_login(panel, app):
    app.tokens.add('listing-test')
    auth = {'X-Token': 'listing-test'}
    path = Path(app.s.hot_folder) / 'art.png'; path.write_bytes(b'initial')
    status, raw, headers = request(panel, '/api/hot-files', headers=auth)
    assert status == 200 and json.loads(raw)[0]['size'] == 7
    tag = headers['ETag']
    status, body, _ = request(panel, '/api/hot-files', headers={**auth, 'If-None-Match': tag})
    assert status == 304 and not body
    path.write_bytes(b'new-content')
    status, raw, headers = request(panel, '/api/hot-files', headers={**auth, 'If-None-Match': tag})
    assert status == 200 and headers['ETag'] != tag and json.loads(raw)[0]['size'] == 11
    status, _, _ = request(panel, '/api/hot-files', headers={'If-None-Match': headers['ETag']})
    assert status == 401


def test_concurrent_calls_scan_one_at_a_time_and_keep_independent_snapshots(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    app = listing_app(tmp_path)
    guard = threading.Lock()
    actual_lock = threading.Lock()
    attempted = 0
    all_attempted, started, release = threading.Event(), threading.Event(), threading.Event()
    scans, active, maximum = [], 0, 0
    class ObservedLock:
        def __enter__(self):
            nonlocal attempted
            with guard:
                attempted += 1
                if attempted == 4:
                    all_attempted.set()
            actual_lock.acquire()
        def __exit__(self, *args):
            actual_lock.release()
    class Entry:
        def __init__(self, index):
            self.name = f'art-{index}.png'
            self.index = index
        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            return SimpleNamespace(st_mode=stat.S_IFREG, st_size=self.index + 1, st_mtime=123.5)
    class Entries:
        def __enter__(self):
            nonlocal active, maximum
            with guard:
                active += 1
                maximum = max(maximum, active)
                self.index = len(scans)
                scans.append(self.index)
            started.set()
            return self
        def __iter__(self):
            assert release.wait(5)
            yield Entry(self.index)
        def __exit__(self, *args):
            nonlocal active
            with guard:
                active -= 1
    app._hot_listing_lock = ObservedLock()
    patch_scandir(monkeypatch, tmp_path, Entries)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(app.list_hot_files) for _ in range(4)]
        try:
            assert started.wait(5) and all_attempted.wait(5)
            assert scans == [0] and maximum == 1
            # O lock de configuracao continua disponivel durante a leitura do disco.
            assert app.settings_lock.acquire(timeout=1)
            app.settings_lock.release()
        finally:
            release.set()
        results = [future.result(timeout=5) for future in futures]
    assert sorted(rows[0]['name'] for rows in results) == [f'art-{i}.png' for i in range(4)]
    assert maximum == 1 and active == 0 and scans == [0, 1, 2, 3]
