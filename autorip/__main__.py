import argparse
import hashlib
import json
import os
import sys
import time
import secrets
from . import __version__
from .config import Settings
from .engine import Rip
from .watcher import watch, run_once, _signature
from .paths import (ProcessLock, next_available_path, manual_journal_path,
                    file_sha256, find_marked_output, write_json_atomic)
from .prt import read_header


_JOURNAL_VERSION = 1


def _settings_fingerprint(s):
    fields = (
        "icc_path", "intent", "black_point_comp", "channel_order", "dpi_x", "dpi_y", "mirror",
        "margin_top_in", "margin_bottom_in", "ink_limit", "white_enabled", "white_alpha_threshold",
        "white_choke_mm", "small_drop_ratio", "white_density", "white_fill_holes_mm", "white_planes",
        "label_enabled",
    )
    settings = {name: getattr(s, name) for name in fields}
    if s.icc_path:
        try:
            settings["icc_sha256"] = file_sha256(s.icc_path)
        except OSError:
            settings["icc_sha256"] = "missing"
    return settings


def _manual_fingerprint(source, signature, s, width_cm):
    payload = {
        "version": __version__,
        "source": os.path.normcase(os.path.realpath(source)),
        "source_signature": list(signature),
        "source_sha256": file_sha256(source),
        "width_cm": width_cm,
        "settings": _settings_fingerprint(s),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest(), payload


def _read_manual_journal(path, canonical_source):
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > 8192:
            return None
        with open(path, encoding="utf-8") as source:
            marker = json.load(source)
        if (not isinstance(marker, dict) or marker.get("version") != _JOURNAL_VERSION
                or marker.get("source") != canonical_source
                or marker.get("phase") not in {"processing", "success", "error"}):
            return None
        return marker
    except (OSError, ValueError, TypeError):
        return None


def _write_manual_metadata(output, info):
    fields = ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_dots", "n_rows", "has_alpha")
    metadata = {key: info[key] for key in fields if key in info}
    write_json_atomic(output + ".meta.json", metadata, prefix=".meta.")


def _manual_output(marker):
    output = find_marked_output(marker)
    if output is None:
        return None
    try:
        read_header(output)
        return output
    except (OSError, ValueError, TypeError):
        return None


def _process_manual_file(source, rip, s, width_cm=None, force=False):
    source = os.fspath(source)
    if os.path.islink(source):
        raise ValueError("A entrada precisa ser um arquivo regular, não um link simbólico.")
    source = os.path.realpath(source)
    signature = _signature(source)
    if signature is None:
        raise ValueError("A entrada precisa ser um arquivo regular, não um link simbólico.")
    fingerprint, identity = _manual_fingerprint(source, signature, s, width_cm)
    canonical = identity["source"]
    journal = manual_journal_path(s.output_folder, source)
    marker = _read_manual_journal(journal, canonical)
    if marker and marker.get("fingerprint") == fingerprint and not force:
        output = _manual_output(marker)
        phase = marker["phase"]
        if phase == "success":
            if output:
                info = marker.get("info") or {}
                if not marker.get("metadata_written"):
                    _write_manual_metadata(output, info)
                    marker["metadata_written"] = True
                    write_json_atomic(journal, marker)
                print(f"Já processado; PRT validado por hash: {output}")
            else:
                print("Journal indica conclusão, mas a saída não está disponível; não vou repetir o RIP automaticamente.")
            return None
        if phase == "error" and output:
            marker.update(phase="success", output=os.path.basename(output))
            info = marker.get("info") or {}
            if info and not marker.get("metadata_written"):
                _write_manual_metadata(output, info)
                marker["metadata_written"] = True
            write_json_atomic(journal, marker)
            print(f"Recuperado sem repetir o RIP; PRT validado por hash: {output}")
            return None
        if phase == "processing" and marker.get("output_sha256"):
            if output:
                marker.update(phase="success", output=os.path.basename(output))
                info = marker.get("info") or {}
                if info and not marker.get("metadata_written"):
                    _write_manual_metadata(output, info)
                    marker["metadata_written"] = True
                write_json_atomic(journal, marker)
                print(f"Recuperado sem repetir o RIP; PRT validado por hash: {output}")
            else:
                print("Journal ambíguo: hash foi preparado antes da publicação, mas o PRT correspondente não foi encontrado. Entrada preservada; confira a pasta de saída antes de usar --force.")
            return None
        # Um marcador processing sem hash prova que a publicação ainda não começou; erro pode ser repetido.

    os.makedirs(os.path.dirname(journal), mode=0o700, exist_ok=True)
    preferred = next_available_path(s.output_folder, os.path.splitext(os.path.basename(source))[0] + ".PRT")
    marker = {
        "version": _JOURNAL_VERSION,
        "job_id": secrets.token_hex(12),
        "phase": "processing",
        "source": canonical,
        "source_signature": list(signature),
        "source_sha256": identity["source_sha256"],
        "fingerprint": fingerprint,
        "output_dir": s.output_folder,
        "output": os.path.basename(preferred),
        "started_ns": time.time_ns(),
        "metadata_written": False,
    }
    write_json_atomic(journal, marker)

    def before_publish(temporary_path, preview):
        marker["output_sha256"] = file_sha256(temporary_path)
        marker["info"] = {key: preview[key] for key in
                           ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_rows", "n_dots", "has_alpha")}
        write_json_atomic(journal, marker)

    try:
        info = rip.process(source, preferred, width_cm, progress=lambda p: print(f"\r{p*100:5.1f}%", end=""),
                           before_publish=before_publish)
        output = info.pop("output_path")
        _write_manual_metadata(output, info)
        marker.update(phase="success", output=os.path.basename(output), metadata_written=True,
                      info={key: info[key] for key in
                            ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_rows", "n_dots", "has_alpha")})
        write_json_atomic(journal, marker)
        print(f"\nConcluído: {output}")
        print(info)
        return info
    except Exception as error:
        marker.update(phase="error", error=f"{type(error).__name__}: {error}"[:500])
        try:
            write_json_atomic(journal, marker)
        except OSError:
            pass
        raise


def main():
    ap = argparse.ArgumentParser(prog="autorip")
    ap.add_argument("--config", default="autorip.json")
    ap.add_argument("--watch", action="store_true", help="modo automatico (hot folder)")
    ap.add_argument("--once", action="store_true", help="processa a hot folder uma vez")
    ap.add_argument("--icc")
    ap.add_argument("--width-cm", type=float)
    ap.add_argument("--no-white", action="store_true")
    ap.add_argument("--gui", action="store_true", help="abre o painel")
    ap.add_argument("--force", action="store_true", help="reprocessa arquivos posicionais mesmo com journal de sucesso")
    ap.add_argument("files", nargs="*", help="arquivos para processar manualmente")
    a = ap.parse_args()
    if a.gui or (not a.files and not a.watch and not a.once):
        from .server import main as gui
        return gui()
    s = Settings.load(a.config)
    if a.icc:
        s.icc_path = a.icc
    if a.no_white:
        s.white_enabled = False
    s.canonicalize_folders()
    s.validate()
    if not os.path.exists(a.config):
        s.save(a.config)
    if a.watch:
        watch(s)
    elif a.once:
        with ProcessLock(os.path.join(s.hot_folder, ".autorip.watch.lock")), \
             ProcessLock(os.path.join(s.output_folder, ".autorip.output.lock")):
            run_once(s, Rip(s))
    else:
        with ProcessLock(os.path.join(s.output_folder, ".autorip.output.lock")):
            rip = Rip(s)
            for file_path in a.files:
                _process_manual_file(file_path, rip, s, a.width_cm, force=a.force)


if __name__ == "__main__":
    main()
