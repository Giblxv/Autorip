import os
import time

from autorip import server as server_module
from conftest import wait_for_job


def test_arquivo_pendente_retentado_sem_reexecutar_o_rip(app, sample_png, monkeypatch):
    original = server_module.move_unique
    failures = {"count": 0}
    recovery = os.path.join(app.home, "archive_recovery")

    def fail_twice(source, folder, name=None):
        if folder in (app.s.done_folder, recovery) and failures["count"] < 2:
            failures["count"] += 1
            raise OSError("falha temporaria de arquivamento")
        return original(source, folder, name)

    monkeypatch.setattr(server_module, "move_unique", fail_twice)
    job = app.enqueue(str(sample_png), 3)
    wait_for_job(job)
    deadline = time.monotonic() + 8
    archived = os.path.join(app.s.done_folder, sample_png.name)
    while time.monotonic() < deadline and not os.path.exists(archived):
        time.sleep(0.05)

    assert failures["count"] == 2
    assert os.path.isfile(archived)
    assert job["status"] == "pronto" and job.get("archive_pending") is False
    assert "Arquivamento recuperado" in job["error"]
    assert len([name for name in os.listdir(app.s.output_folder) if name.lower().endswith(".prt")]) == 1
