import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from autorip import prt, watcher
from autorip.config import Settings
from autorip.engine import Rip
from autorip.paths import file_sha256, find_marked_output


@pytest.mark.parametrize("channels", [1, 4, 12])
@pytest.mark.parametrize("width", [1, 37, 5669])
def test_writer_digest_matches_complete_file_with_padding_and_multiple_blocks(tmp_path, channels, width):
    path = tmp_path / "stream.PRT"
    data = np.random.default_rng(5).integers(0, 4, (13, width), dtype=np.uint8)
    writer = prt.PrtWriter(path, 720, 2400, 13, width, channels, hash_output=True)
    for start, end in ((0, 4), (4, 11), (11, 13)):
        plane = data[start:end]
        planes = [plane if index % 2 == 0 else plane[:, ::-1] for index in range(channels)]
        writer.write_block(planes)
        assert writer.output_sha256 is None
    writer.close()
    assert writer.output_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    writer.close()
    assert writer.output_sha256 == file_sha256(path)


def test_ordinary_writer_never_constructs_a_digest(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("hash desnecessario")
    monkeypatch.setattr(prt, "hashlib", SimpleNamespace(sha256=forbidden))
    writer = prt.PrtWriter(tmp_path / "plain.PRT", 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    assert writer.output_sha256 is None


@pytest.mark.parametrize("failure", ["incomplete", "fsync"])
def test_digest_is_not_exposed_when_close_fails(tmp_path, monkeypatch, failure):
    writer = prt.PrtWriter(tmp_path / "failed.PRT", 300, 300, 2, 8, hash_output=True)
    writer.write_block([np.zeros((1 if failure == "incomplete" else 2, 8), dtype=np.uint8)] * 12)
    if failure == "fsync":
        def failed(_fd):
            raise OSError("fsync falhou")
        monkeypatch.setattr(prt.os, "fsync", failed)
    with pytest.raises((RuntimeError, OSError)):
        writer.close()
    assert writer.f.closed and writer.output_sha256 is None


@pytest.mark.parametrize("requested", [False, True, "true", 1, None])
def test_engine_digest_is_explicit_callback_metadata_only(tmp_path, sample_png, monkeypatch, requested):
    builds = []
    def digest():
        builds.append(True)
        return hashlib.sha256()
    monkeypatch.setattr(prt, "hashlib", SimpleNamespace(sha256=digest))
    observed = []
    def before_publish(path, info):
        assert Path(path).is_file()
        if requested is True:
            assert info["output_sha256"] == file_sha256(path)
        else:
            assert "output_sha256" not in info
        observed.append(dict(info))
    before_publish.requires_output_sha256 = requested
    result = Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
        str(sample_png), str(tmp_path / "out.PRT"), width_cm=1.27, before_publish=before_publish)
    assert len(observed) == 1 and len(builds) == int(requested is True)
    assert "output_sha256" not in result
    if requested is True:
        assert observed[0]["output_sha256"] == file_sha256(result["output_path"])


def test_callback_failure_still_removes_temporary_and_prevents_publication(tmp_path, sample_png):
    def before_publish(path, info):
        assert info["output_sha256"] == file_sha256(path)
        raise RuntimeError("journal indisponivel")
    before_publish.requires_output_sha256 = True
    destination = tmp_path / "out.PRT"
    with pytest.raises(RuntimeError, match="journal indisponivel"):
        Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
            str(sample_png), str(destination), width_cm=1.27, before_publish=before_publish)
    assert not destination.exists() and not list(tmp_path.glob("*.part"))


class LegacyRip:
    """Simula um motor antigo que não reconhece o atributo do callback."""
    def __init__(self, rip):
        self.rip = rip

    def process(self, *args, before_publish=None, **kwargs):
        def forward(path, info):
            before_publish(path, info)
        return self.rip.process(*args, before_publish=forward, **kwargs)


@pytest.mark.parametrize("legacy", [False, True])
def test_watcher_uses_stream_digest_and_preserves_legacy_readback(tmp_path, sample_png, monkeypatch, legacy):
    folders = {name: tmp_path / name for name in ("hot", "out", "done", "error")}
    folders["hot"].mkdir()
    (folders["hot"] / "source.png").write_bytes(Path(sample_png).read_bytes())
    settings = Settings(dpi_x=300, dpi_y=300, label_enabled=False,
                        hot_folder=str(folders["hot"]), output_folder=str(folders["out"]),
                        done_folder=str(folders["done"]), error_folder=str(folders["error"]))
    monkeypatch.setattr(watcher, "_stable_files", lambda paths, wait=1: [(p, watcher._signature(p)) for p in paths])
    reads, markers = [], []
    def readback(path):
        reads.append(path)
        return file_sha256(path)
    original = watcher.write_archive_marker
    def journal(source, value):
        markers.append(copy.deepcopy(value))
        return original(source, value)
    monkeypatch.setattr(watcher, "file_sha256", readback)
    monkeypatch.setattr(watcher, "write_archive_marker", journal)
    rip = Rip(settings)
    assert watcher.run_once(settings, LegacyRip(rip) if legacy else rip, log=lambda _: None) == 1
    assert len(reads) == int(legacy)
    output = folders["out"] / "source.PRT"
    marker = next(marker for marker in markers if marker.get("output_sha256"))
    assert marker["output_sha256"] == file_sha256(output)
    assert find_marked_output(marker) == str(output)
    with output.open("r+b") as stream:
        stream.seek(-1, 2)
        last = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes([last[0] ^ 255]))
    assert find_marked_output(marker) is None


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("move", [False, True])
def test_panel_worker_uses_digest_only_for_archived_jobs(app, sample_png, monkeypatch, legacy, move):
    from autorip import server
    from conftest import wait_for_job

    reads, markers = [], []
    def readback(path, *args, **kwargs):
        reads.append(path)
        return file_sha256(path, *args, **kwargs)
    original = server.write_archive_marker
    def journal(source, value):
        markers.append(copy.deepcopy(value))
        return original(source, value)
    monkeypatch.setattr(server, "file_sha256", readback)
    monkeypatch.setattr(server, "write_archive_marker", journal)
    if legacy:
        app.rip = LegacyRip(app.rip)
    job = app.enqueue(str(sample_png), move_to_done=move)
    wait_for_job(job)
    assert job["status"] == "pronto", job
    temporary_reads = [path for path in reads if str(path).endswith(".part")]
    assert len(temporary_reads) == int(legacy and move)
    if move:
        marker = next(marker for marker in markers if marker.get("output_sha256")
                      and marker.get("output_dir") == app.s.output_folder)
        assert marker["output_sha256"] == file_sha256(job["out"])
    else:
        assert not any(marker.get("output_sha256") for marker in markers)
