import os
import shutil
import time

import numpy as np

from autorip import watcher as watcher_module
from autorip.config import Settings
from autorip.engine import Rip
from autorip.paths import write_archive_marker
from autorip.prt import PrtWriter
from autorip.watcher import _recover_marked, run_once


def test_run_once_reivindica_arquiva_e_nao_sobrescreve(app_home, sample_png, tmp_path):
    hot = tmp_path / "watch-hot"
    output = tmp_path / "watch-out"
    done = tmp_path / "watch-done"
    errors = tmp_path / "watch-error"
    source = hot / "arte.png"
    hot.mkdir()
    shutil.copyfile(sample_png, source)
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False,
                        hot_folder=str(hot), output_folder=str(output),
                        done_folder=str(done), error_folder=str(errors))
    rip = Rip(settings)

    assert run_once(settings, rip, log=lambda _message: None) == 1
    assert len(list(output.glob("arte_*.PRT"))) == 1
    assert len(list(output.glob("arte_*.PRT.meta.json"))) == 1
    assert (done / "arte.png").is_file()
    assert not source.exists()

    hot.mkdir(exist_ok=True)
    shutil.copyfile(sample_png, source)
    assert run_once(settings, rip, log=lambda _message: None) == 1
    assert len(list(output.glob("arte_*.PRT"))) == 2
    assert (done / "arte_001.png").is_file()


def test_arquivo_corrompido_vai_para_pasta_de_erro(tmp_path):
    hot, output, done, errors = (tmp_path / name for name in ("hot", "out", "done", "errors"))
    hot.mkdir()
    (hot / "quebrado.png").write_bytes(b"nao e uma imagem")
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False,
                        hot_folder=str(hot), output_folder=str(output),
                        done_folder=str(done), error_folder=str(errors))
    assert run_once(settings, Rip(settings), log=lambda _message: None) == 0
    assert (errors / "quebrado.png").is_file()
    assert not list(output.glob("*.PRT"))


def test_mudanca_de_hot_folder_mantem_recuperacao_antiga(app, sample_png, tmp_path):
    old_hot = app.s.hot_folder
    processing = os.path.join(old_hot, ".autorip_processing")
    os.makedirs(processing, exist_ok=True)
    abandoned = os.path.join(processing, "interrompido.png")
    shutil.copyfile(sample_png, abandoned)
    new_hot = tmp_path / "nova-entrada"
    app.apply_settings({"hot_folder": str(new_hot), "auto_mode": True, "poll_seconds": 0.25})

    deadline = time.monotonic() + 15
    archived = os.path.join(app.s.done_folder, "interrompido.png")
    job = None
    while time.monotonic() < deadline:
        job = next((item for item in app.jobs if item["name"] == "interrompido.png"), None)
        if (job and job["status"] in ("pronto", "erro")
                and os.path.isfile(archived) and not os.path.exists(abandoned)):
            break
        time.sleep(0.05)

    assert job is not None and job["status"] == "pronto"
    assert not os.path.exists(abandoned)
    assert os.path.isfile(archived)
    assert os.path.isfile(os.path.join(app.home, "hot_folders.json"))


def test_run_once_repete_arquivamento_sem_reprocessar(monkeypatch, sample_png, tmp_path):
    hot, output, done, errors = (tmp_path / name for name in ("retry-hot", "retry-out", "retry-done", "retry-error"))
    hot.mkdir()
    shutil.copyfile(sample_png, hot / "retry.png")
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False,
                        hot_folder=str(hot), output_folder=str(output),
                        done_folder=str(done), error_folder=str(errors))
    recovery = os.path.join(str(hot), ".autorip_archive_recovery")
    original = watcher_module.move_unique
    failures = {"count": 0}

    def fail_twice(source, folder, name=None):
        if folder in (str(done), recovery) and failures["count"] < 2:
            failures["count"] += 1
            raise OSError("temporary archive error")
        return original(source, folder, name)

    monkeypatch.setattr(watcher_module, "move_unique", fail_twice)
    seen, archive_pending = {}, {}
    assert watcher_module.run_once(settings, Rip(settings), log=lambda _message: None,
                                   seen=seen, archive_pending=archive_pending) == 1
    assert len(archive_pending) == 1
    # Simula reinício: os dicionários de deduplicação/retry em memória são novos.
    assert watcher_module.run_once(settings, Rip(settings), log=lambda _message: None,
                                   seen={}, archive_pending={}) == 0
    assert (done / "retry.png").is_file()
    assert len(list(output.glob("*.PRT"))) == 1


def _write_valid_prt(path):
    writer = PrtWriter(str(path), 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()


def test_watcher_error_nao_associa_prt_homonimo_sem_hash(sample_png, tmp_path):
    hot, output, done, errors = (tmp_path / name for name in ("hot-e", "out-e", "done-e", "errors-e"))
    processing = hot / ".autorip_processing"
    processing.mkdir(parents=True)
    source = processing / "homonimo.png"
    shutil.copyfile(sample_png, source)
    prt = output / "homonimo.PRT"
    output.mkdir()
    _write_valid_prt(prt)
    settings = Settings(hot_folder=str(hot), output_folder=str(output), done_folder=str(done),
                        error_folder=str(errors), printed_folder=str(tmp_path / "printed-e"))
    write_archive_marker(str(source), {"phase": "error", "target": "error", "output": prt.name,
                                       "output_dir": str(output),
                                       "source_signature": list(watcher_module._signature(str(source)))})

    assert _recover_marked(str(source), settings, lambda _message: None, {}, {}) is True
    assert (errors / source.name).is_file()
    assert not (done / source.name).exists()


def test_watcher_processing_sem_hash_nao_associa_prt_homonimo(sample_png, tmp_path):
    hot, output, done, errors = (tmp_path / name for name in ("hot-p", "out-p", "done-p", "errors-p"))
    processing = hot / ".autorip_processing"
    processing.mkdir(parents=True)
    source = processing / "pendente.png"
    shutil.copyfile(sample_png, source)
    prt = output / "pendente.PRT"
    output.mkdir()
    _write_valid_prt(prt)
    settings = Settings(hot_folder=str(hot), output_folder=str(output), done_folder=str(done),
                        error_folder=str(errors), printed_folder=str(tmp_path / "printed-p"))
    write_archive_marker(str(source), {"phase": "processing", "target": "done", "output": prt.name,
                                       "output_dir": str(output),
                                       "source_signature": list(watcher_module._signature(str(source)))})

    assert _recover_marked(str(source), settings, lambda _message: None, {}, {}) is False
    assert source.is_file()
    assert prt.is_file()
    assert not (done / source.name).exists()


def test_watcher_success_sem_hash_exato_vai_para_erros(sample_png, tmp_path):
    hot, output, done, errors = (tmp_path / name for name in ("hot-s", "out-s", "done-s", "errors-s"))
    processing = hot / ".autorip_processing"
    processing.mkdir(parents=True)
    source = processing / "hash-ausente.png"
    shutil.copyfile(sample_png, source)
    output.mkdir()
    prt = output / "hash-ausente.PRT"
    _write_valid_prt(prt)
    settings = Settings(hot_folder=str(hot), output_folder=str(output), done_folder=str(done),
                        error_folder=str(errors), printed_folder=str(tmp_path / "printed-s"))
    write_archive_marker(str(source), {"phase": "success", "target": "done", "output": prt.name,
                                       "output_dir": str(output), "output_sha256": "f" * 64,
                                       "source_signature": list(watcher_module._signature(str(source)))})

    assert _recover_marked(str(source), settings, lambda _message: None, {}, {}) is True
    assert (errors / source.name).is_file()
    assert not (done / source.name).exists()
    assert prt.is_file()


def test_watcher_continua_se_arte_some_apos_listar_processamento(
        tmp_path, sample_png, monkeypatch):
    hot, out, done, error = (tmp_path / n for n in ("hot", "out", "done", "error"))
    processing = hot / ".autorip_processing"
    processing.mkdir(parents=True)
    disappeared = processing / "a-sumiu.png"
    valid = processing / "b-valida.png"
    shutil.copyfile(sample_png, disappeared)
    shutil.copyfile(sample_png, valid)
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False,
                        hot_folder=str(hot), output_folder=str(out),
                        done_folder=str(done), error_folder=str(error))
    original = watcher_module._signature

    def signature_with_race(path):
        if os.fspath(path) == str(disappeared):
            disappeared.unlink(missing_ok=True)
            raise FileNotFoundError("arquivo removido entre listdir e stat")
        return original(path)

    monkeypatch.setattr(watcher_module, "_signature", signature_with_race)
    assert run_once(settings, Rip(settings), log=lambda _message: None) == 1
    assert len(list(out.glob("b-valida_*.PRT"))) == 1
    assert (done / "b-valida.png").is_file()
    assert not (out / "a-sumiu.PRT").exists()


def test_watcher_journal_ilegivel_bloqueia_rip_e_deduplica_alerta(tmp_path, sample_png):
    hot, output, done, errors = (tmp_path / n for n in ("hot", "out", "done", "errors"))
    processing = hot / ".autorip_processing"
    processing.mkdir(parents=True)
    source = processing / "pedido-antigo.png"
    shutil.copyfile(sample_png, source)
    marker = processing / "pedido-antigo.png.autorip.json"
    marker.write_text('{"version":1,"phase":"success"', encoding="utf-8")
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False,
                        hot_folder=str(hot), output_folder=str(output),
                        done_folder=str(done), error_folder=str(errors))
    logs, alerts = [], set()
    assert run_once(settings, Rip(settings), log=logs.append,
                    invalid_journal_alerts=alerts) == 0
    assert run_once(settings, Rip(settings), log=logs.append,
                    invalid_journal_alerts=alerts) == 0
    assert source.is_file() and marker.is_file()
    assert not list(output.glob("*.PRT"))
    assert sum("Journal invalido" in item for item in logs) == 1

    marker.unlink()
    assert run_once(settings, Rip(settings), log=logs.append,
                    invalid_journal_alerts=alerts) == 1
    assert len(list(output.glob("pedido-antigo_*.PRT"))) == 1
