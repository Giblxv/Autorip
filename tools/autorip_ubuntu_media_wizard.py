"""Assistente Windows para preparar a mídia Ubuntu do servidor AutoRIP."""
from __future__ import annotations

import json
import subprocess
import threading
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from media_security import download, manifest_sha256, sha256, verify_rufus_signature

VERSION = "0.8.13"
UBUNTU_URL = "https://releases.ubuntu.com/24.04/ubuntu-24.04.3-desktop-amd64.iso"
UBUNTU_SUMS_URL = "https://releases.ubuntu.com/24.04/SHA256SUMS"
RELEASE_BASE = f"https://github.com/Giblxv/Autorip/releases/download/v{VERSION}"
BUNDLE_URL = f"{RELEASE_BASE}/autorip-linux-server-bundle-{VERSION}.zip"
BUNDLE_SHA_URL = f"{RELEASE_BASE}/autorip-{VERSION}-sha256.txt"
RUFUS_URL = "https://rufus.ie/downloads/rufus-4.15p.exe"
MAX_UBUNTU_ISO_BYTES = 8 * 1024**3
MAX_BUNDLE_BYTES = 256 * 1024**2
MAX_MANIFEST_BYTES = 64 * 1024
MAX_RUFUS_BYTES = 32 * 1024**2


def ubuntu_expected_sha():
    request = urllib.request.Request(UBUNTU_SUMS_URL, headers={"User-Agent": "AutoRIP-Media-Wizard"})
    with urllib.request.urlopen(request, timeout=60) as response:
        for line in response.read().decode("utf-8", "replace").splitlines():
            if UBUNTU_URL.rsplit("/", 1)[-1] in line:
                return line.split()[0]
    raise RuntimeError("O checksum do Ubuntu não foi encontrado.")


def main():
    root = tk.Tk()
    root.title("AutoRIP — assistente de mídia Ubuntu")
    root.geometry("720x470")
    root.minsize(640, 400)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)

    title = ttk.Label(root, text="Assistente de servidor AutoRIP", font=("Segoe UI", 18, "bold"))
    title.grid(row=0, column=0, padx=24, pady=(22, 4), sticky="w")
    intro = ttk.Label(root, text=(
        "Este assistente baixa o Ubuntu, valida o arquivo, baixa o pacote do AutoRIP "
        "e abre o Rufus para criar a mídia inicializável. O disco escolhido no Rufus "
        "será apagado somente após sua confirmação naquela ferramenta."), wraplength=660)
    intro.grid(row=1, column=0, padx=24, sticky="w")

    frame = ttk.Frame(root, padding=24)
    frame.grid(row=2, column=0, sticky="nsew")
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="Pasta de preparação:").grid(row=0, column=0, sticky="w", pady=6)
    folder = tk.StringVar(value=str(Path.home() / "Downloads" / "AutoRIP-Ubuntu-Media"))
    ttk.Entry(frame, textvariable=folder).grid(row=0, column=1, sticky="ew", padx=8, pady=6)
    ttk.Button(frame, text="Escolher", command=lambda: folder.set(filedialog.askdirectory() or folder.get())).grid(row=0, column=2, pady=6)

    status = tk.StringVar(value="Pronto para iniciar.")
    ttk.Label(frame, textvariable=status, wraplength=640).grid(row=1, column=0, columnspan=3, sticky="w", pady=(18, 6))
    progress = ttk.Progressbar(frame, mode="indeterminate")
    progress.grid(row=2, column=0, columnspan=3, sticky="ew", pady=6)
    log = tk.Text(frame, height=10, state="disabled", wrap="word")
    log.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=8)
    frame.rowconfigure(3, weight=1)

    def report(message):
        root.after(0, lambda: (status.set(message), log.config(state="normal"), log.insert("end", message + "\n"), log.see("end"), log.config(state="disabled")))

    def run():
        try:
            base = Path(folder.get()).expanduser().resolve()
            base.mkdir(parents=True, exist_ok=True)
            iso = download(UBUNTU_URL, base / "ubuntu-24.04.3-desktop-amd64.iso", report, MAX_UBUNTU_ISO_BYTES)
            report("Validando SHA-256 do Ubuntu...")
            expected = ubuntu_expected_sha()
            actual = sha256(iso)
            if actual.lower() != expected.lower():
                raise RuntimeError("O checksum do Ubuntu não confere; o arquivo foi removido por segurança.")
            report("Ubuntu validado com sucesso.")
            bundle = download(BUNDLE_URL, base / f"autorip-linux-server-bundle-{VERSION}.zip", report, MAX_BUNDLE_BYTES)
            sums = download(BUNDLE_SHA_URL, base / f"autorip-{VERSION}-sha256.txt", report, MAX_MANIFEST_BYTES)
            expected_bundle = manifest_sha256(sums.read_text(encoding="utf-8"), bundle.name)
            if sha256(bundle).lower() != expected_bundle:
                bundle.unlink(missing_ok=True)
                raise RuntimeError("O checksum do pacote Linux não confere; o arquivo foi removido por segurança.")
            rufus = download(RUFUS_URL, base / "rufus-4.15p.exe", report, MAX_RUFUS_BYTES)
            verify_rufus_signature(rufus)
            profile = {"version": VERSION, "ubuntu_iso": str(iso), "autorip_bundle": str(bundle), "rufus": str(rufus)}
            (base / "media-plan.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
            report("Downloads e validações concluídos. Abrindo o Rufus...")
            subprocess.Popen([str(rufus), str(iso)], cwd=str(base))
            root.after(0, lambda: messagebox.showinfo(
                "Próximo passo",
                "No Rufus, selecione cuidadosamente o pendrive/SSD correto e confirme a gravação. "
                "Todos os dados do disco selecionado serão apagados. Depois do boot pelo USB, use o pacote AutoRIP salvo na pasta de preparação."))
        except Exception as exc:
            error_message = str(exc)
            root.after(0, lambda: messagebox.showerror("Falha", error_message))
            report("Falha: " + error_message)
        finally:
            root.after(0, lambda: (progress.stop(), start.configure(state="normal")))

    def start_run():
        if not messagebox.askyesno("Confirmar preparação", "O Rufus será aberto para preparar uma mídia. Você deverá confirmar o disco correto dentro dele. Continuar?"):
            return
        start.configure(state="disabled")
        progress.start(12)
        threading.Thread(target=run, daemon=True).start()

    start = ttk.Button(root, text="Baixar e preparar mídia Ubuntu", command=start_run)
    start.grid(row=3, column=0, padx=24, pady=(0, 10), sticky="w")
    ttk.Button(root, text="Abrir documentação", command=lambda: webbrowser.open("https://github.com/Giblxv/Autorip/releases")).grid(row=3, column=0, padx=250, pady=(0, 10), sticky="w")
    root.mainloop()


if __name__ == "__main__":
    main()
