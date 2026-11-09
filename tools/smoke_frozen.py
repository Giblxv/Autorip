"""Exercita o executável real: inicialização, login, upload, PRT e encerramento."""
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

from PIL import Image


def smoke(executable, expected_version):
    with tempfile.TemporaryDirectory(prefix="autorip-smoke-") as folder:
        home = Path(folder)
        config = dict(auto_mode=False, offline_mode=True, auto_update=False,
                      label_enabled=False, dpi_x=72, dpi_y=72,
                      margin_top_in=0, margin_bottom_in=0, poll_seconds=.25)
        (home / "autorip.json").write_text(json.dumps(config), encoding="utf-8")
        env = dict(os.environ, AUTORIP_HOME=str(home), AUTORIP_NOBROWSER="1")
        # O bootloader Windows pode manter stdout válido quando o chamador o
        # redireciona. Nesse caso main() não cria autorip.log: capture ambos.
        with (home / "console.log").open("wb") as capture:
            process = subprocess.Popen([str(Path(executable).resolve()), "--web"], env=env,
                                       stdout=capture, stderr=subprocess.STDOUT)
            token = ""
            base = None

            def logs():
                return "\n".join(path.read_text(encoding="utf-8", errors="replace")
                                 for path in (home / "autorip.log", home / "console.log")
                                 if path.exists())

            def api(path, data=None, raw=None):
                payload = raw if raw is not None else json.dumps(data).encode() if data is not None else None
                headers = {"X-Token": token}
                if payload is not None:
                    headers["Content-Type"] = "application/octet-stream" if raw is not None else "application/json"
                request = Request(base + path, data=payload, headers=headers)
                with urlopen(request, timeout=10) as response:
                    return json.load(response)

            try:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"Executavel encerrou antes de iniciar: {process.returncode}")
                    match = re.search(r"AutoRIP em (http://127\.0\.0\.1:\d+)/", logs())
                    if match:
                        base = match.group(1)
                        break
                    time.sleep(.25)
                if base is None:
                    raise TimeoutError("Executavel nao informou endereco local em 90 segundos")
                state = api("/api/state")
                if state.get("version") != expected_version:
                    raise RuntimeError(f"Versao do executavel inesperada: {state.get('version')}")
                token = api("/api/setpass", {"new": "Smoke-test-only-123"})["token"]
                image = io.BytesIO()
                Image.new("RGBA", (72, 72), (20, 140, 210, 255)).save(image, format="PNG")
                job = api("/api/upload?name=smoke.png&width=2.54", raw=image.getvalue())
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    state = api("/api/state")
                    result = next((item for item in state["jobs"] if item["id"] == job["id"]), None)
                    if result and result["status"] == "erro":
                        raise RuntimeError(f"RIP do executavel falhou: {result.get('error')}")
                    if result and result["status"] == "pronto":
                        break
                    time.sleep(.25)
                else:
                    raise TimeoutError("RIP nao terminou em 60 segundos")
                prints = api("/api/prints")
                if not prints or abs(prints[0]["width_cm"] - 2.54) > .01:
                    raise RuntimeError("PRT nao apareceu na fila com a medida esperada")
                files = list((home / "saida").glob("*.PRT"))
                if len(files) != 1 or files[0].stat().st_size <= 48:
                    raise RuntimeError("Executavel nao publicou um PRT completo")
                api("/api/shutdown", {})
                process.wait(timeout=20)
                if process.returncode:
                    raise RuntimeError(f"Executavel encerrou com codigo {process.returncode}")
                print(f"Smoke test aprovado: AutoRIP {expected_version}, login, upload, PRT 2.54 cm e encerramento.")
            except BaseException:
                print(logs()[-5000:])
                raise
            finally:
                if process.poll() is None:
                    if os.name == "nt":
                        # Encerre também o filho do bootloader one-file, que mantém
                        # os locks e o diretório temporário abertos no Windows.
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=15, check=False)
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("expected_version")
    args = parser.parse_args()
    smoke(args.executable, args.expected_version)
