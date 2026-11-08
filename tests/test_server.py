import json
import os
import sys
import time
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import numpy as np
from autorip.paths import file_sha256, write_archive_marker
from autorip.paths import ProcessLock
from autorip.prt import PrtWriter

from autorip import server as server_module
from conftest import wait_for_job


def _source_signature(path):
    return list(server_module._signature(path))


def test_main_headless_nao_abre_navegador(monkeypatch):
    called = []
    monkeypatch.setattr(server_module, "run_direct", lambda: called.append(True))
    monkeypatch.setattr(sys, "argv", ["AutoRIP.exe", "--headless"])
    monkeypatch.delenv("AUTORIP_NOBROWSER", raising=False)

    server_module.main()

    assert called == [True]


def test_main_direct_inicia_worker_nativo(monkeypatch):
    called = []
    monkeypatch.setattr(server_module, "run_direct", lambda: called.append(True))
    monkeypatch.setattr(sys, "argv", ["AutoRIP.exe", "--direct"])
    server_module.main()
    assert called == [True]


def test_main_exe_por_padrao_e_nativo(monkeypatch):
    called = []
    monkeypatch.setattr(server_module, "run_direct", lambda: called.append(True))
    monkeypatch.setattr(sys, "argv", ["AutoRIP.exe"])
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    server_module.main()
    assert called == [True]


@pytest.fixture
def panel(app, monkeypatch):
    monkeypatch.setattr(server_module, "APP", app)
    http = ThreadingHTTPServer(("127.0.0.1", 0), server_module.H)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{http.server_address[1]}"
    try:
        yield base
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


def request(base, path, method="GET", data=None, headers=None):
    request_headers = dict(headers or {})
    if data is not None:
        request_headers.setdefault("Content-Type", "application/json")
    req = Request(base + path, data=data, method=method, headers=request_headers)
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, response.read(), response.headers
    except HTTPError as error:
        return error.code, error.read(), error.headers


def test_painel_rejeita_host_remoto_e_porta_incorreta(panel):
    porta = int(panel.rsplit(":", 1)[1])
    for host in (f"evil.example:{porta}", f"127.0.0.1:{porta + 1}",
                 f"127.0.0.1:{porta}@evil.example"):
        status, body, _ = request(panel, "/api/state", headers={"Host": host})
        assert status == 403
        assert json.loads(body)["error"] == "host local nao autorizado"
        status, _, _ = request(panel, "/api/login", "POST",
                               json.dumps({"password": "qualquer"}).encode(),
                               headers={"Host": host})
        assert status == 403

    status, _, _ = request(panel, "/api/state",
                           headers={"Host": f"localhost:{porta}"})
    assert status == 200


def test_configuracoes_nao_revelam_segredos_e_resposta_tem_headers(panel, app):
    app.s.trello_token = "TOKEN-QUE-NAO-PODE-SAIR"
    app.tokens.add("sessao-teste")
    status, body, headers = request(panel, "/api/settings", headers={"X-Token": "sessao-teste"})
    result = json.loads(body)
    assert status == 200
    assert result["trello_token"] == ""
    assert result["_secret_configured"]["trello_token"] is True
    assert b"TOKEN-QUE-NAO-PODE-SAIR" not in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_endpoint_logo_nao_serve_caminho_arbitrario(panel, app, tmp_path):
    secret = tmp_path / "nao-publicar.png"
    secret.write_bytes(b"conteudo local")
    app.s.brand_logo = str(secret)
    status, body, _ = request(panel, "/api/brand-logo")
    assert status == 404 and b"conteudo local" not in body


def test_endpoint_thumb_nao_serve_symlink_externo(panel, app, tmp_path):
    outside = tmp_path / "segredo.jpg"
    outside.write_bytes(b"segredo")
    thumbs = os.path.join(app.home, "thumbs", "by_name")
    os.makedirs(thumbs, exist_ok=True)
    link = os.path.join(thumbs, "falso.jpg")
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink indisponível neste sistema")
    app.tokens.add("token-thumb")
    status, body, _ = request(panel, "/api/thumb?name=falso",
                              headers={"X-Token": "token-thumb"})
    assert status == 404 and b"segredo" not in body


def test_journal_recupera_entrada_ripada_sem_duplicar(panel, app, sample_png):
    source = os.path.join(app.processing_folder, "recuperar.png")
    os.makedirs(app.processing_folder, exist_ok=True)
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    output = os.path.join(app.s.output_folder, "recuperar.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    info = {"width_cm": 1.0, "height_cm": 1.0, "dpi_x": 300, "dpi_y": 300,
            "n_rows": 1, "n_dots": 8, "has_alpha": True}
    write_archive_marker(source, {"phase": "success", "target": "done", "output": "recuperar.PRT",
                                  "output_dir": app.s.output_folder, "output_sha256": file_sha256(output),
                                  "job_id": "recuperacao", "info": info,
                                  "metadata_written": False, "outbox_handled": False,
                                  "source_signature": _source_signature(source)})
    app.apply_settings({"auto_mode": False, "poll_seconds": 0.25})

    deadline = time.monotonic() + 10
    archived = os.path.join(app.s.done_folder, "recuperar.png")
    while time.monotonic() < deadline and not os.path.exists(archived):
        time.sleep(0.05)

    assert os.path.isfile(archived)
    assert not os.path.exists(source)
    assert len([name for name in os.listdir(app.s.output_folder) if name.endswith(".PRT")]) == 1


def test_journal_recupera_upload_manual_pendente(app, sample_png):
    folder = os.path.join(app.inbox, "interrompido")
    os.makedirs(folder)
    source = os.path.join(folder, "manual.png")
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    output = os.path.join(app.s.output_folder, "manual.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    info = {"width_cm": 1.0, "height_cm": 1.0, "dpi_x": 300, "dpi_y": 300,
            "n_rows": 1, "n_dots": 8, "has_alpha": True}
    write_archive_marker(source, {"phase": "success", "target": "done", "output": "manual.PRT",
                                  "output_dir": app.s.output_folder, "output_sha256": file_sha256(output),
                                  "job_id": "manual", "info": info,
                                  "metadata_written": False, "outbox_handled": False,
                                  "source_signature": _source_signature(source)})

    deadline = time.monotonic() + 10
    archived = os.path.join(app.s.done_folder, "manual.png")
    while time.monotonic() < deadline and not os.path.exists(archived):
        time.sleep(0.05)

    assert os.path.isfile(archived)
    assert not os.path.exists(folder)
    assert app.auto is False


def test_limpeza_de_upload_manual_re_tenta_lock_temporario(app, monkeypatch):
    folder = os.path.join(app.inbox, "retry-cleanup")
    os.makedirs(folder)
    original_rmdir = os.rmdir
    attempts = {"count": 0}

    def flaky_rmdir(path):
        if path == os.path.realpath(folder) and attempts["count"] < 2:
            attempts["count"] += 1
            raise PermissionError("arquivo ainda sendo liberado")
        return original_rmdir(path)

    monkeypatch.setattr(server_module.os, "rmdir", flaky_rmdir)
    app._cleanup_manual_folder(os.path.join(folder, "arte.png"))
    assert attempts["count"] == 2
    assert not os.path.exists(folder)


def test_journal_recria_sidecar_e_outbox_apos_crash_de_publicacao(app, sample_png):
    from autorip import integrations

    folder = os.path.join(app.inbox, "crash-apos-publish")
    os.makedirs(folder)
    source = os.path.join(folder, "arte.png")
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    output = os.path.join(app.s.output_folder, "arte.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    app.s.webhook_url = "https://example.test/hook"
    info = {"width_cm": 2.5, "height_cm": 1.5, "dpi_x": 300, "dpi_y": 300,
            "n_rows": 10, "n_dots": 20, "has_alpha": True}
    write_archive_marker(source, {
        "phase": "processing", "target": "done", "output": "arte.PRT",
        "output_dir": app.s.output_folder, "output_sha256": file_sha256(output),
        "job_id": "crash-job-1", "name": "arte.png", "info": info,
        "metadata_written": False, "outbox_handled": False,
        "source_signature": _source_signature(source),
    })

    assert app._recover_marked_source(source, app.s) is True
    assert os.path.isfile(os.path.join(app.s.done_folder, "arte.png"))
    with open(output + ".meta.json", encoding="utf-8") as metadata_file:
        assert json.load(metadata_file)["width_cm"] == 2.5
    outbox = integrations.outbox_load(app.home)
    assert len(outbox) == 1
    assert outbox[0]["job_id"] == "crash-job-1"
    assert outbox[0]["job"]["out"] == output


def test_journal_error_nao_associa_prt_homonimo_sem_hash(app, sample_png):
    source = os.path.join(app.processing_folder, "homonimo.png")
    os.makedirs(app.processing_folder, exist_ok=True)
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    output = os.path.join(app.s.output_folder, "homonimo.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    write_archive_marker(source, {"phase": "error", "target": "error", "output": "homonimo.PRT",
                                  "output_dir": app.s.output_folder, "job_id": "falhou",
                                  "source_signature": _source_signature(source)})

    assert app._recover_marked_source(source, app.s) is True
    assert os.path.isfile(os.path.join(app.s.error_folder, "homonimo.png"))
    assert not os.path.exists(os.path.join(app.s.done_folder, "homonimo.png"))


def test_journal_processing_sem_hash_nao_associa_prt_homonimo(app, sample_png):
    source = os.path.join(app.processing_folder, "pendente.png")
    os.makedirs(app.processing_folder, exist_ok=True)
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    output = os.path.join(app.s.output_folder, "pendente.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    write_archive_marker(source, {"phase": "processing", "target": "done", "output": "pendente.PRT",
                                  "output_dir": app.s.output_folder, "job_id": "interrompido",
                                  "source_signature": _source_signature(source)})

    assert app._recover_marked_source(source, app.s) is False
    assert os.path.isfile(source)
    assert os.path.isfile(output)
    assert not os.path.exists(os.path.join(app.s.done_folder, "pendente.png"))


def test_journal_nao_se_aplica_a_arquivo_substituido_no_mesmo_caminho(app, sample_png):
    source = os.path.join(app.processing_folder, "substituido.png")
    os.makedirs(app.processing_folder, exist_ok=True)
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    original_signature = _source_signature(source)
    output = os.path.join(app.s.output_folder, "substituido.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    with open(source, "ab") as changed:
        changed.write(b"changed")
    write_archive_marker(source, {"phase": "success", "target": "done", "output": "substituido.PRT",
                                  "output_dir": app.s.output_folder, "output_sha256": file_sha256(output),
                                  "source_signature": original_signature})

    assert app._recover_marked_source(source, app.s) is True
    assert os.path.isfile(os.path.join(app.s.error_folder, "substituido.png"))
    assert not os.path.exists(os.path.join(app.s.done_folder, "substituido.png"))


def test_journal_success_sem_prt_do_hash_exato_vai_para_revisao(app, sample_png):
    source = os.path.join(app.processing_folder, "hash-ausente.png")
    os.makedirs(app.processing_folder, exist_ok=True)
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    output = os.path.join(app.s.output_folder, "hash-ausente.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    write_archive_marker(source, {"phase": "success", "target": "done", "output": "hash-ausente.PRT",
                                  "output_dir": app.s.output_folder, "output_sha256": "f" * 64,
                                  "source_signature": _source_signature(source), "job_id": "hash-ausente",
                                  "info": {"width_cm": 1.0, "height_cm": 1.0}})

    assert app._recover_marked_source(source, app.s) is True
    assert os.path.isfile(os.path.join(app.s.error_folder, "hash-ausente.png"))
    assert not os.path.exists(os.path.join(app.s.done_folder, "hash-ausente.png"))
    assert os.path.isfile(output)


def test_lock_de_output_antigo_e_liberado_apos_job_ativo(app, tmp_path):
    old_output = app.s.output_folder
    old_lock = ProcessLock(os.path.join(old_output, ".autorip.output.lock")).acquire()
    app._output_locks.append(old_lock)
    app._active_output_key = app._output_lock_key(old_output)
    new_output = str(tmp_path / "novo-output")

    app.apply_settings({"output_folder": new_output})
    assert old_lock._file is not None
    assert len(app._output_locks) == 2

    app._finish_output_use()
    assert old_lock._file is None
    assert len(app._output_locks) == 1
    assert app._output_locks[0]._file is not None


def test_recovery_retry_sidecar_nao_fica_bloqueado_no_mesmo_processo(app, sample_png, monkeypatch):
    source = os.path.join(app.processing_folder, "retry-sidecar.png")
    os.makedirs(app.processing_folder, exist_ok=True)
    with open(sample_png, "rb") as origin, open(source, "wb") as target:
        target.write(origin.read())
    output = os.path.join(app.s.output_folder, "retry-sidecar.PRT")
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    info = {"width_cm": 2.0, "height_cm": 1.0, "dpi_x": 300, "dpi_y": 300,
            "n_rows": 1, "n_dots": 8, "has_alpha": True}
    write_archive_marker(source, {"phase": "processing", "target": "done", "output": "retry-sidecar.PRT",
                                  "output_dir": app.s.output_folder, "output_sha256": file_sha256(output),
                                  "job_id": "retry-sidecar-job", "name": "retry-sidecar.png", "info": info,
                                  "metadata_written": False, "outbox_handled": False,
                                  "source_signature": _source_signature(source)})
    app.s.poll_seconds = 0.25
    original = app._write_output_metadata
    attempts = {"count": 0}

    def fail_once(path, metadata):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("temporary sidecar failure")
        return original(path, metadata)

    monkeypatch.setattr(app, "_write_output_metadata", fail_once)
    archived = os.path.join(app.s.done_folder, "retry-sidecar.png")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not os.path.isfile(archived):
        time.sleep(0.05)

    assert os.path.isfile(archived)
    assert attempts["count"] >= 2
    assert os.path.isfile(output + ".meta.json")
    assert len([name for name in os.listdir(app.s.output_folder) if name.endswith(".PRT")]) == 1


def test_hot_folder_retry_sidecar_apos_enqueue_no_mesmo_processo(app, sample_png, monkeypatch):
    import shutil

    alias = os.path.join(os.path.dirname(app.s.hot_folder), "hot-folder-alias")
    try:
        os.symlink(app.s.hot_folder, alias, target_is_directory=True)
    except OSError:
        pytest.skip("symlink indisponivel neste ambiente")
    app.apply_settings({"hot_folder": alias})
    assert app.s.hot_folder == os.path.realpath(alias)
    app.s.poll_seconds = 0.25
    app.auto = True
    source = os.path.join(app.s.hot_folder, "hot-retry.png")
    os.makedirs(app.s.hot_folder, exist_ok=True)
    shutil.copyfile(sample_png, source)
    original = app._write_output_metadata
    attempts = {"count": 0}

    def fail_once(path, metadata):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("temporary sidecar failure after publish")
        return original(path, metadata)

    monkeypatch.setattr(app, "_write_output_metadata", fail_once)
    archived = os.path.join(app.s.done_folder, "hot-retry.png")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not os.path.isfile(archived):
        time.sleep(0.05)

    assert os.path.isfile(archived)
    assert attempts["count"] >= 2
    assert os.path.isfile(os.path.join(app.s.output_folder, "hot-retry.PRT.meta.json"))
    assert len([name for name in os.listdir(app.s.output_folder) if name.endswith(".PRT")]) == 1


def test_troca_de_senha_revoga_sessoes_anteriores(panel, app):
    origin = {"Origin": panel, "Sec-Fetch-Site": "same-origin"}
    first = json.dumps({"new": "senha-inicial-123"}).encode()
    status, body, _ = request(panel, "/api/setpass", "POST", first, origin)
    assert status == 200
    old_token = json.loads(body)["token"]
    assert old_token

    status, body, _ = request(panel, "/api/setpass", "POST",
        json.dumps({"password": "senha-inicial-123", "new": "nova-senha-456"}).encode(),
        {**origin, "X-Token": old_token})
    assert status == 200
    new_token = json.loads(body)["token"]
    assert new_token != old_token

    status, _, _ = request(panel, "/api/settings", headers={"X-Token": old_token})
    assert status == 401
    status, _, _ = request(panel, "/api/settings", headers={"X-Token": new_token})
    assert status == 200

    status, _, _ = request(panel, "/api/login", "POST",
        json.dumps({"password": "senha-inicial-123"}).encode(), origin)
    assert status == 401


def test_post_cross_site_e_operacoes_sem_sessao_sao_bloqueados(panel, app):
    body = json.dumps({"on": False}).encode()
    status, _, _ = request(panel, "/api/auto", "POST", body, {
        "Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site", "X-Token": "sessao-teste"})
    assert status == 403
    origin = {"Origin": panel, "Sec-Fetch-Site": "same-origin"}
    status, _, _ = request(panel, "/api/auto", "POST", body, origin)
    assert status == 401
    app.tokens.add("sessao-teste")
    status, response, _ = request(panel, "/api/auto", "POST", body,
                                  {**origin, "X-Token": "sessao-teste"})
    assert status == 200 and json.loads(response)["auto"] is False


def test_upload_rejeita_sessao_ausente_ou_invalida(panel, app, sample_png, monkeypatch):
    raw = sample_png.read_bytes()
    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        pytest.fail("Upload sem sessao nao pode chegar ao disco nem a fila")

    monkeypatch.setattr(app, "receive_upload", forbidden)
    for headers in (
        {"Content-Type": "application/octet-stream"},
        {"Content-Type": "application/octet-stream", "X-Token": "invalido"},
    ):
        status, body, _ = request(panel, "/api/upload?name=nao-autorizado.png",
                                  "POST", raw, headers)
        assert status == 401
        assert json.loads(body)["error"] == "login"
    assert called == []


def test_primeiro_acesso_exige_senha_forte_e_upload_validado(panel, app, sample_png, monkeypatch):
    origin = {"Origin": panel, "Sec-Fetch-Site": "same-origin"}
    weak = json.dumps({"new": "1234"}).encode()
    status, _, _ = request(panel, "/api/setpass", "POST", weak, origin)
    assert status == 400 and not app.has_pass()
    too_long = json.dumps({"new": "x" * 129}).encode()
    status, _, _ = request(panel, "/api/setpass", "POST", too_long, origin)
    assert status == 400 and not app.has_pass()

    strong = json.dumps({"new": "senha-de-teste-123"}).encode()
    status, body, _ = request(panel, "/api/setpass", "POST", strong, origin)
    token = json.loads(body)["token"]
    assert status == 200 and app.has_pass()
    long_password = json.dumps({"password": "x" * 129}).encode()
    status, _, _ = request(panel, "/api/login", "POST", long_password, origin)
    assert status == 400

    raw = sample_png.read_bytes()
    headers = {**origin, "Content-Type": "application/octet-stream", "X-Token": token}
    pending = os.path.join(app.inbox, "pendente")
    os.makedirs(pending)
    with open(os.path.join(pending, "reserva.bin"), "wb") as target:
        target.write(b"x")
    with monkeypatch.context() as scoped:
        scoped.setattr(server_module, "MAX_MANUAL_PENDING_BYTES", len(raw))
        status, _, _ = request(panel, "/api/upload?name=quota.png", "POST", raw, headers)
        assert status == 413
        assert app._manual_pending_bytes() == 1
    os.remove(os.path.join(pending, "reserva.bin"))
    os.rmdir(pending)
    status, body, _ = request(panel, "/api/upload?name=%3Cscript%3E.png&width=3", "POST", raw, headers)
    assert status == 202
    identifier = json.loads(body)["id"]
    job = next(job for job in app.jobs if job["id"] == identifier)
    wait_for_job(job)
    assert job["status"] == "pronto"
    assert job["name"] == "_script_.png"

    status, _, _ = request(panel, "/api/settings", headers={"X-Token": token})
    assert status == 200
    status, _, _ = request(panel, "/api/upload?name=evil.png", "POST", raw,
                           {"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert status == 403


def test_worker_sobrevive_a_arte_removida_antes_do_processamento(app, sample_png, tmp_path):
    from conftest import wait_for_job

    missing = tmp_path / "arte-removida.png"
    missing.write_bytes(sample_png.read_bytes())
    missing.unlink()

    # A primeira falha nao pode matar o worker que processa o pedido seguinte.
    failed = app.enqueue(str(missing), width_cm=2.54, move_to_done=True)
    valid = app.enqueue(str(sample_png), width_cm=2.54, move_to_done=False)
    wait_for_job(failed, timeout=15)
    wait_for_job(valid, timeout=30)

    assert failed["status"] == "erro"
    assert valid["status"] == "pronto"
    assert valid["out"] and os.path.isfile(valid["out"])
    assert not (tmp_path / "arte-removida.png.autorip.json").exists()
    assert str(missing) not in app.archive_pending


def test_modo_automatico_persiste_entre_reinicios(panel, app):
    from autorip.config import Settings

    app.tokens.add("sessao-auto")
    headers = {"X-Token": "sessao-auto", "Origin": panel, "Sec-Fetch-Site": "same-origin"}
    for enabled in (True, False):
        status, body, _ = request(panel, "/api/auto", "POST",
                                  json.dumps({"on": enabled}).encode(), headers)
        assert status == 200
        assert json.loads(body)["auto"] is enabled
        assert app.auto is enabled
        assert app.s.auto_mode is enabled
        assert Settings.load(app.cfg_path, base=app.home).auto_mode is enabled


def test_modo_automatico_nao_ativa_se_salvar_configuracao_falhar(
        panel, app, monkeypatch):
    from autorip.config import Settings

    app.tokens.add("sessao-auto")
    previous = app.auto
    assert previous is False

    def cannot_save(self, path):
        raise OSError("disco indisponivel durante a persistencia")

    monkeypatch.setattr(Settings, "save", cannot_save)
    status, _, _ = request(panel, "/api/auto", "POST",
                           json.dumps({"on": True}).encode(),
                           {"X-Token": "sessao-auto", "Origin": panel})
    assert status == 500
    assert app.auto is previous
    assert app.s.auto_mode is False
    assert json.loads(open(app.cfg_path, encoding="utf-8").read())["auto_mode"] is False

def test_estado_e_fila_nao_divulgam_artes_sem_login(panel, app):
    app.log("SEGREDO-DE-PEDIDO-PRIVADO")
    app.jobs.append({"name": "CLIENTE-PRIVADO.png", "status": "fila"})
    app.tokens.add("sessao-read")
    status, body, _ = request(panel, "/api/state")
    data = json.loads(body)
    assert status == 200 and data["locked"] is True
    assert data["has_pass"] is False
    assert data["version"]
    for key in ("jobs", "log", "hot_folder", "output_folder", "icc", "auto"):
        assert key not in data
    assert b"SEGREDO-DE-PEDIDO-PRIVADO" not in body
    assert b"CLIENTE-PRIVADO" not in body

    status, _, _ = request(panel, "/api/prints")
    assert status == 401
    status, authorized, _ = request(panel, "/api/state",
                                    headers={"X-Token": "sessao-read"})
    assert status == 200
    public = json.loads(authorized)
    assert "jobs" in public and "log" in public
    assert public["jobs"][-1]["name"] == "CLIENTE-PRIVADO.png"


def test_previa_jpeg_requer_autenticacao(panel, app):
    import pathlib

    root = pathlib.Path(app.home) / "thumbs"
    root.mkdir(exist_ok=True)
    (root / "pedido.jpg").write_bytes(b"JPEG-PRIVADO")
    status, body, _ = request(panel, "/api/thumb?id=pedido")
    assert status == 401 and b"JPEG-PRIVADO" not in body

    app.tokens.add("sessao-thumb")
    status, body, headers = request(panel, "/api/thumb?id=pedido",
                                    headers={"X-Token": "sessao-thumb"})
    assert status == 200 and body == b"JPEG-PRIVADO"
    assert headers["Content-Type"] == "image/jpeg"


def test_tela_login_atualiza_atividade_sem_revelar_jobs(panel, app, monkeypatch):
    before = server_module.LAST_CLIENT_SEEN
    status, body, _ = request(panel, "/api/state")
    assert status == 200 and json.loads(body)["locked"] is True
    assert server_module.LAST_CLIENT_SEEN >= before

def test_excluir_prt_apaga_metadados_e_miniaturas_associadas(app):
    path = os.path.join(app.s.output_folder, "remover.PRT")
    writer = PrtWriter(path, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    with open(path + ".meta.json", "w", encoding="utf-8") as metadata:
        metadata.write("{}")

    root = os.path.join(app.home, "thumbs")
    by_name = os.path.join(root, "by_name")
    os.makedirs(by_name, exist_ok=True)
    named = os.path.join(by_name, "remover.jpg")
    job_preview = os.path.join(root, "job-teste.jpg")
    unrelated = os.path.join(by_name, "outra-arte.jpg")
    for thumbnail in (named, job_preview, unrelated):
        with open(thumbnail, "wb") as target:
            target.write(b"preview")

    job = {"id": "job-teste", "out": path, "thumb": "/api/thumb?id=job-teste"}
    app.jobs.append(job)
    app.delete_print("remover.PRT")
    assert not os.path.exists(path)
    assert not os.path.exists(path + ".meta.json")
    assert not os.path.exists(named)
    assert not os.path.exists(job_preview)
    assert os.path.isfile(unrelated)
    assert job["thumb"] == ""


def test_excluir_prt_nao_segue_symlink_de_thumbnail(app, tmp_path):
    path = os.path.join(app.s.output_folder, "seguro.PRT")
    writer = PrtWriter(path, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    outside = tmp_path / "externo.jpg"
    outside.write_bytes(b"nao remover")
    by_name = os.path.join(app.home, "thumbs", "by_name")
    os.makedirs(by_name, exist_ok=True)
    link = os.path.join(by_name, "seguro.jpg")
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks indisponiveis")
    app.delete_print("seguro.PRT")
    assert outside.read_bytes() == b"nao remover"



def test_thumbnail_so_substitui_jpeg_apos_gravacao_completa(tmp_path, monkeypatch):
    from PIL import Image

    destination = tmp_path / "preview.jpg"
    picture = Image.new("RGB", (12, 12), (10, 20, 30))
    server_module._save_thumbnail_atomic(picture, str(destination))
    with Image.open(destination) as stored:
        stored.verify()
    original = destination.read_bytes()

    def broken_save(self, target, *args, **kwargs):
        target.write(b"imagem-incompleta")
        raise OSError("falha simulada ao salvar preview")

    monkeypatch.setattr(Image.Image, "save", broken_save)
    with pytest.raises(OSError, match="falha simulada"):
        server_module._save_thumbnail_atomic(picture, str(destination))

    assert destination.read_bytes() == original
    assert not list(tmp_path.glob(".thumb.*.part"))


def test_geracao_de_preview_recusa_diretorio_symlink(app, sample_png, tmp_path):
    outside = tmp_path / "imagens-externas"
    outside.mkdir()
    link = os.path.join(app.home, "thumbs")
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink de diretorio indisponivel")
    assert app._thumb("job-symlink", str(sample_png)) == ""
    assert not list(outside.iterdir())



def test_journal_ilegivel_bloqueia_reprocessamento_automatico(app, sample_png, tmp_path):
    import shutil

    source = tmp_path / "origem-sem-reconciliacao.png"
    shutil.copyfile(sample_png, source)
    marker = tmp_path / "origem-sem-reconciliacao.png.autorip.json"
    marker.write_text('{"version":1,"phase":"success","output":"arquivo.PRT"', encoding="utf-8")
    def warnings():
        return [item for item in app.log_lines
                if "journal invalido" in item.lower() and source.name in item]

    warnings_before = len(warnings())
    assert app._recover_marked_source(str(source), app.s) is True
    assert app._recover_marked_source(str(source), app.s) is True
    assert source.is_file()
    assert marker.is_file()
    assert len(warnings()) == warnings_before + 1

    # Remover manualmente o registro invalido libera a arte para nova analise.
    marker.unlink()
    assert app._recover_marked_source(str(source), app.s) is False


def test_journal_symlink_bloqueia_rip_e_preserva_evidencia(app, sample_png, tmp_path):
    import shutil

    source = tmp_path / "com-marcador-symlink.png"
    shutil.copyfile(sample_png, source)
    external = tmp_path / "evidencia.json"
    external.write_text("conteudo-externo", encoding="utf-8")
    marker = tmp_path / "com-marcador-symlink.png.autorip.json"
    try:
        os.symlink(external, marker)
    except (OSError, NotImplementedError):
        pytest.skip("symlink indisponivel")
    assert app._recover_marked_source(str(source), app.s) is True
    assert marker.is_symlink()
    assert external.read_text(encoding="utf-8") == "conteudo-externo"
    assert source.is_file()

def _idle_monitor_fake_app():
    """Contexto isolado para evitar consumir a fila do worker real nos testes."""
    import queue
    from types import SimpleNamespace
    from autorip.config import Settings

    return SimpleNamespace(
        settings_lock=threading.RLock(), lock=threading.RLock(),
        auto=False, s=Settings(), queued_sources=set(),
        archive_pending={}, q=queue.Queue())


def test_navegador_ocioso_nao_encerra_producao_ativa():
    state = _idle_monitor_fake_app()
    assert server_module._can_close_idle_browser(state) is True

    state.auto = True
    assert server_module._can_close_idle_browser(state) is False
    state.auto = False

    state.queued_sources.add("trabalho-em-rip")
    assert server_module._can_close_idle_browser(state) is False
    state.queued_sources.clear()

    state.q.put(("pendente", "arte.png", None, True))
    assert server_module._can_close_idle_browser(state) is False
    state.q.get_nowait()

    state.archive_pending["arquivo-pendente"] = ("destino", None, "erros", 100, 0)
    assert server_module._can_close_idle_browser(state) is False
    state.archive_pending.clear()

    assert server_module._can_close_idle_browser(state) is True


def test_navegador_ocioso_nao_encerra_monitoramento_trello_ativo():
    state = _idle_monitor_fake_app()
    state.s.offline_mode = False
    state.s.trello_key = "KEY"
    state.s.trello_token = "TOKEN"
    state.s.trello_in_list = "LIST"
    assert server_module._can_close_idle_browser(state) is False

    state.s.offline_mode = True
    assert server_module._can_close_idle_browser(state) is True

@pytest.mark.parametrize("missing_tk", [False, True])
def test_modo_direto_sem_janela_inicia_servidor_sem_browser(monkeypatch, missing_tk):
    import sys
    from types import SimpleNamespace
    from autorip import server

    class DisplayUnavailable(Exception):
        pass

    def unavailable():
        raise DisplayUnavailable("no display")

    fake = None if missing_tk else SimpleNamespace(Tk=unavailable, TclError=DisplayUnavailable)
    monkeypatch.setitem(sys.modules, "tkinter", fake)
    calls = []
    monkeypatch.setattr(server, "serve", lambda **kwargs: calls.append(kwargs))
    server.run_direct()
    assert calls == [{"open_browser": False}]
