"""Fila controlada por passos: disputa pausa/retomada sem sleeps nem threads de RIP."""
import json
import os
import queue
import shutil
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest

from autorip import server


class WorkerIdle(BaseException):
    pass


class StepQueue(queue.Queue):
    after_get = None

    def get(self, *args, **kwargs):
        try:
            item = super().get(block=False)
        except queue.Empty:
            raise WorkerIdle()
        callback, self.after_get = self.after_get, None
        if callback:
            callback()
        return item


@pytest.fixture
def idle_app(app_home):
    class IdleApp(server.App):
        def _worker(self):
            pass

        def _watch(self):
            pass

    app = IdleApp()
    app.q = StepQueue()
    return app


def drain(app):
    with pytest.raises(WorkerIdle):
        server.App._worker(app)


def source(app, sample_png, name="arte.png"):
    path = os.path.join(app.processing_folder, name)
    shutil.copyfile(sample_png, path)
    return path


def test_lote_grande_mantem_todos_os_jobs_controlaveis(idle_app):
    jobs = [idle_app.enqueue(os.path.join(idle_app.processing_folder, f"arte-{i}.png")) for i in range(80)]
    assert len(idle_app.jobs) == 80
    assert idle_app.control_job(jobs[0]["id"], "pause")["status"] == "pausado"
    assert idle_app.control_job(jobs[-1]["id"], "cancel")["status"] == "cancelando"


def test_limite_inclui_pausados_fora_da_fila_e_libera_apos_cancelar(idle_app, sample_png, monkeypatch):
    monkeypatch.setattr(server, "MAX_PENDING_JOBS", 3)
    paths = [source(idle_app, sample_png, f"paused-{i}.png") for i in range(3)]
    jobs = [idle_app.enqueue(path) for path in paths]
    for job in jobs:
        idle_app.control_job(job["id"], "pause")
    drain(idle_app)
    assert idle_app.q.empty()
    assert all(job["status"] == "pausado" for job in jobs)
    assert idle_app.enqueue(paths[0]) is jobs[0]
    with pytest.raises(RuntimeError, match="Fila cheia"):
        idle_app.enqueue(os.path.join(idle_app.processing_folder, "overflow.png"))
    idle_app.control_job(jobs[0]["id"], "cancel")
    drain(idle_app)
    replacement = idle_app.enqueue(os.path.join(idle_app.processing_folder, "replacement.png"))
    assert replacement["status"] == "fila" and len(idle_app.queued_sources) == 3


@pytest.mark.parametrize("move", [False, True])
def test_pausa_retomada_antes_do_worker_executa_exatamente_um_rip(idle_app, sample_png, monkeypatch, move):
    path = source(idle_app, sample_png)
    job = idle_app.enqueue(path, move_to_done=move)
    idle_app.control_job(job["id"], "pause")
    idle_app.control_job(job["id"], "resume")
    assert idle_app.q.qsize() == 1
    original = idle_app.rip.process
    calls = []

    def counted(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(idle_app.rip, "process", counted)
    drain(idle_app)
    assert calls == [path]
    assert job["status"] == "pronto"
    assert len([name for name in os.listdir(idle_app.s.output_folder) if name.endswith(".PRT")]) == 1
    assert not idle_app.job_controls and not idle_app.queued_sources


def test_retomada_entre_get_e_transicao_do_worker_nao_duplica_item(idle_app, sample_png):
    path = source(idle_app, sample_png)
    job = idle_app.enqueue(path, move_to_done=False)
    idle_app.control_job(job["id"], "pause")
    idle_app.q.after_get = lambda: idle_app.control_job(job["id"], "resume")
    drain(idle_app)
    assert job["status"] == "pronto"
    assert len([name for name in os.listdir(idle_app.s.output_folder) if name.endswith(".PRT")]) == 1


def test_cancelar_pausado_ja_consumido_preserva_arte_e_libera_slot(idle_app, sample_png):
    path = source(idle_app, sample_png)
    job = idle_app.enqueue(path)
    idle_app.control_job(job["id"], "pause")
    drain(idle_app)
    assert job["status"] == "pausado" and idle_app.q.empty()
    idle_app.control_job(job["id"], "cancel")
    idle_app.control_job(job["id"], "cancel")
    assert idle_app.q.qsize() == 1
    drain(idle_app)
    assert job["status"] == "cancelado"
    assert os.path.isfile(os.path.join(idle_app.s.error_folder, "arte.png"))
    assert not os.path.exists(path)
    assert not idle_app.queued_sources and not idle_app.job_controls
    assert not [name for name in os.listdir(idle_app.s.output_folder) if name.endswith(".PRT")]


@pytest.mark.parametrize("interruption", [server.JobPaused, server.JobCancelled])
def test_cancelamento_durante_interrupcao_nao_fica_preso(idle_app, sample_png, monkeypatch, interruption):
    path = source(idle_app, sample_png)
    job = idle_app.enqueue(path)

    def paused_with_cancel(*args, **kwargs):
        idle_app.control_job(job["id"], "cancel")
        raise interruption()

    monkeypatch.setattr(idle_app.rip, "process", paused_with_cancel)
    drain(idle_app)
    assert job["status"] == "cancelado"
    assert not idle_app.queued_sources and not idle_app.job_controls
    assert os.path.isfile(os.path.join(idle_app.s.error_folder, "arte.png"))


def test_historico_limita_concluidos_sem_remover_pausado_antigo(idle_app):
    paused = idle_app.enqueue(os.path.join(idle_app.processing_folder, "paused.png"))
    idle_app.control_job(paused["id"], "pause")
    for i in range(80):
        path = os.path.join(idle_app.processing_folder, f"done-{i}.png")
        job = idle_app.enqueue(path)
        job["status"] = "pronto"
        idle_app._release_source(path)
    assert len(idle_app.jobs) == 51 and paused in idle_app.jobs
    assert sum(job["status"] == "pronto" for job in idle_app.jobs) == 50
    assert idle_app.control_job(paused["id"], "resume")["status"] == "fila"


def test_conclusao_tardia_de_job_antigo_entra_no_historico_recente(idle_app):
    path = os.path.join(idle_app.processing_folder, "antigo.png")
    old = idle_app.enqueue(path)
    idle_app.control_job(old["id"], "pause")
    for i in range(80):
        other_path = os.path.join(idle_app.processing_folder, f"novo-{i}.png")
        job = idle_app.enqueue(other_path)
        job["status"] = "pronto"
        idle_app._release_source(other_path)
    old["status"] = "pronto"
    idle_app._release_source(path)
    assert len(idle_app.jobs) == 50
    assert idle_app.jobs[-1] is old
    with idle_app.lock:
        assert idle_app._retained_jobs(server.MAX_STATE_HISTORY)[-1] is old


def test_estado_inclui_todos_ativos_e_so_12_concluidos(idle_app, monkeypatch):
    for i in range(20):
        path = os.path.join(idle_app.processing_folder, f"old-{i}.png")
        job = idle_app.enqueue(path)
        idle_app.q.get()
        job["status"] = "pronto"
        idle_app._release_source(path)
    active = [idle_app.enqueue(os.path.join(idle_app.processing_folder, f"live-{i}.png")) for i in range(100)]
    idle_app.tokens.add("queue-test")
    monkeypatch.setattr(server, "APP", idle_app)
    with ThreadingHTTPServer(("127.0.0.1", 0), server.H) as http:
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f"http://127.0.0.1:{http.server_port}/api/state", headers={"X-Token": "queue-test"})
            with urlopen(request, timeout=10) as response:
                state = json.load(response)
        finally:
            http.shutdown()
            thread.join(timeout=2)
    assert {job["id"] for job in active} <= {job["id"] for job in state["jobs"]}
    assert len(state["jobs"]) == 112
    assert state["queue_used"] == 100 and state["queue_limit"] == 100


def test_fila_cheia_permite_retomar_sem_criar_novo_slot(idle_app):
    jobs = [idle_app.enqueue(os.path.join(idle_app.processing_folder, f"paused-{i}.png")) for i in range(100)]
    for job in jobs:
        idle_app.control_job(job["id"], "pause")
    drain(idle_app)
    idle_app.control_job(jobs[0]["id"], "resume")
    assert idle_app.q.qsize() == 1 and len(idle_app.queued_sources) == 100
    with pytest.raises(RuntimeError, match="Fila cheia"):
        idle_app.enqueue(os.path.join(idle_app.processing_folder, "overflow.png"))
    assert len(idle_app.jobs) == 100 and len(idle_app.job_controls) == 100
