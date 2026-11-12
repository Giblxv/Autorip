import gc
import json
import os
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from autorip import integrations as mod


def store(home, items):
    mod._atomic_json(mod._outbox_path(home), items)


def _patch_loader(monkeypatch, callback, *homes):
    original = mod.outbox_load
    targets = {os.path.normcase(os.path.abspath(home)) for home in homes}

    def scoped(home):
        if os.path.normcase(os.path.abspath(home)) in targets:
            return callback(home)
        return original(home)

    monkeypatch.setattr(mod, 'outbox_load', scoped)


def spy_loader(monkeypatch, *homes):
    original = mod.outbox_load
    calls = []

    def load(home):
        calls.append(home)
        return original(home)

    _patch_loader(monkeypatch, load, *homes)
    return calls


def test_count_reuses_validation_and_tracks_add_remove(tmp_path, monkeypatch):
    calls = spy_loader(monkeypatch, tmp_path)
    counter = mod.OutboxCounter()
    assert counter.count(tmp_path) == 0
    store(tmp_path, [{}, {}])
    assert counter.count(tmp_path) == counter.count(tmp_path) == 2
    assert len(calls) == 2
    os.remove(mod._outbox_path(tmp_path))
    assert counter.count(tmp_path) == 0
    store(tmp_path, [{}])
    assert counter.count(tmp_path) == 1


def test_atomic_replacement_same_size_mtime_is_detected(tmp_path):
    path = tmp_path / 'outbox.json'
    path.write_text('[{}]    ')
    counter = mod.OutboxCounter()
    assert counter.count(tmp_path) == 1
    previous = path.stat()
    replacement = tmp_path / 'replacement'
    replacement.write_text('[{}, {}]')
    os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    os.replace(replacement, path)
    assert path.stat().st_size == previous.st_size
    assert counter.count(tmp_path) == 2


@pytest.mark.parametrize('items', [None, {}, ['bad'], [{'sent': 'bad'}],
                                   [{'sent': [3]}], [{'required': False}],
                                   [{'required': [False]}]])
def test_invalid_content_never_returns_old_count(tmp_path, items):
    counter = mod.OutboxCounter()
    store(tmp_path, [{}])
    assert counter.count(tmp_path) == 1
    store(tmp_path, items)
    for _ in range(2):
        with pytest.raises(ValueError):
            counter.count(tmp_path)
    store(tmp_path, [])
    assert counter.count(tmp_path) == 0


def test_expiration_revalidates_unchanged_file(tmp_path, monkeypatch):
    store(tmp_path, [{}])
    now = [10.0]
    monkeypatch.setattr(mod, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    calls = spy_loader(monkeypatch, tmp_path)
    counter = mod.OutboxCounter()
    assert counter.count(tmp_path) == 1
    now[0] += mod.OUTBOX_COUNT_CACHE_SECONDS - .01
    assert counter.count(tmp_path) == 1 and len(calls) == 1
    now[0] += .02
    assert counter.count(tmp_path) == 1 and len(calls) == 2


def test_replacement_during_validation_is_not_cached(tmp_path, monkeypatch):
    store(tmp_path, [{}])
    original = mod.outbox_load
    calls = []

    def replace_after_read(home):
        value = original(home)
        calls.append(True)
        if len(calls) == 1:
            store(home, [{}, {}])
        return value

    _patch_loader(monkeypatch, replace_after_read, tmp_path)
    counter = mod.OutboxCounter()
    assert counter.count(tmp_path) == 1
    assert counter.count(tmp_path) == counter.count(tmp_path) == 2
    assert len(calls) == 2


def test_multiple_readers_share_one_decode(tmp_path, monkeypatch):
    store(tmp_path, [{}] * 42)
    started, release = threading.Event(), threading.Event()
    original = mod.outbox_load
    calls = []

    def blocked(home):
        calls.append(True)
        started.set()
        assert release.wait(3)
        return original(home)

    _patch_loader(monkeypatch, blocked, tmp_path)
    counter = mod.OutboxCounter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        first = pool.submit(counter.count, tmp_path)
        try:
            assert started.wait(3)
            remaining = [pool.submit(counter.count, tmp_path) for _ in range(7)]
        finally:
            release.set()
        assert [first.result()] + [f.result() for f in remaining] == [42] * 8
    assert len(calls) == 1


def test_counter_retains_no_decoded_jobs(tmp_path, monkeypatch):
    class Payload(list):
        pass
    refs = []

    def load(_home):
        value = Payload([{'job': {'name': 'private.png'}}])
        refs.append(weakref.ref(value))
        return value

    _patch_loader(monkeypatch, load, tmp_path)
    counter = mod.OutboxCounter()
    assert counter.count(tmp_path) == 1
    gc.collect()
    assert refs[0]() is None


def test_counter_keeps_only_last_home(tmp_path, monkeypatch):
    first, second = tmp_path / 'one', tmp_path / 'two'
    store(first, [{}]); store(second, [{}, {}])
    calls = spy_loader(monkeypatch, first, second)
    counter = mod.OutboxCounter()
    assert [counter.count(first), counter.count(second), counter.count(first)] == [1, 2, 1]
    assert len(calls) == 3


def test_stat_failure_does_not_mask_error(tmp_path, monkeypatch):
    store(tmp_path, [{}])
    counter = mod.OutboxCounter()
    assert counter.count(tmp_path) == 1
    original = counter._signature
    monkeypatch.setattr(counter, '_signature', lambda _path: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        counter.count(tmp_path)
    monkeypatch.setattr(counter, '_signature', original)
    store(tmp_path, [])
    assert counter.count(tmp_path) == 0


def test_relative_home_stays_bound_if_cwd_changes_during_read(tmp_path, monkeypatch):
    first = tmp_path / 'one'
    other = tmp_path / 'other'
    store(first, [{}, {}, {}])
    store(other / 'one', [{}])
    original = mod.outbox_load

    def change_directory(home):
        monkeypatch.chdir(other)
        return original(home)

    monkeypatch.chdir(tmp_path)
    _patch_loader(monkeypatch, change_directory, first)
    assert mod.OutboxCounter().count('one') == 3
