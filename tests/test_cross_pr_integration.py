"""Regressoes cruzadas dos PRs #16-#30: sem impressora e sem API externa."""
import errno
import os
from pathlib import Path

import numpy as np
from PIL import Image

from autorip import paths, updater
from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import PrtWriter, read_header
from tools.check_release_version import release_versions, validate_release_tag


def test_preview_atomico_e_remocao_do_trabalho_andam_juntos(app, sample_png):
    output = Path(app.s.output_folder) / "integrado.PRT"
    writer = PrtWriter(output, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()

    thumb = app._thumb("integracao-job", str(sample_png), output_name="integrado")
    assert thumb == "/api/thumb?id=integracao-job"
    root = Path(app.home) / "thumbs"
    by_job = root / "integracao-job.jpg"
    by_name = root / "by_name" / "integrado.jpg"
    for path in (by_job, by_name):
        with Image.open(path) as preview:
            assert preview.format == "JPEG"
            preview.verify()

    job = {"id": "integracao-job", "out": str(output), "thumb": thumb}
    app.jobs.append(job)
    app.delete_print("integrado.PRT")
    assert job["thumb"] == ""
    assert not output.exists()
    assert not by_job.exists()
    assert not by_name.exists()
    assert not list(root.glob(".thumb.*.part"))
    assert not list((root / "by_name").glob(".thumb.*.part"))


def test_rip_publica_prt_integro_quando_hardlink_falha(tmp_path, sample_png, monkeypatch):
    def bloqueia_hardlink(*_args, **_kwargs):
        raise OSError(errno.EPERM, "hardlink indisponivel (teste)")

    monkeypatch.setattr(paths.os, "link", bloqueia_hardlink)
    output = tmp_path / "resultado-integrado.PRT"
    rip = Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False, white_enabled=False))
    rip.process(str(sample_png), str(output), width_cm=2.54)

    header = read_header(output)
    assert header["n_dots"] == 300
    assert header["n_rows"] > 0
    assert output.stat().st_size > 0
    assert not list(tmp_path.glob(".publish.*.part"))
    assert not list(tmp_path.glob("*.part"))


def test_versao_estavel_da_release_e_aceita_pelo_atualizador():
    root = Path(__file__).resolve().parents[1]
    python_version, installer_version = release_versions(root)
    assert python_version == installer_version
    tag = "v" + python_version
    assert validate_release_tag(tag, root) == python_version
    assert updater._safe_release_tag(tag)
