import os
import sys
import tempfile

import numpy as np
import pytest

from autorip import __main__ as cli
from autorip.config import Settings
from autorip.paths import publish_unique_file
from autorip.prt import PrtWriter


def test_cli_positional_recupera_journal_sem_duplicar(monkeypatch, tmp_path, sample_png):
    output = tmp_path / "out"
    config = tmp_path / "autorip.json"
    settings = Settings(
        auto_mode=False,
        offline_mode=True,
        label_enabled=False,
        dpi_x=300,
        dpi_y=300,
        margin_top_in=0,
        margin_bottom_in=0,
        hot_folder=str(tmp_path / "hot"),
        output_folder=str(output),
        printed_folder=str(tmp_path / "printed"),
        done_folder=str(tmp_path / "done"),
        error_folder=str(tmp_path / "error"),
    )
    settings.save(str(config))

    class CrashOnceRip:
        calls = 0

        def __init__(self, _settings):
            pass

        def process(self, source, preferred, width_cm=None, progress=None, before_publish=None):
            type(self).calls += 1
            fd, temporary = tempfile.mkstemp(prefix=".fake-prt.", suffix=".part", dir=os.path.dirname(preferred))
            os.close(fd)
            try:
                writer = PrtWriter(temporary, 300, 300, 1, 8)
                writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
                writer.close()
                info = {"width_cm": 2.0, "height_cm": 1.0, "dpi_x": 300, "dpi_y": 300,
                        "n_rows": 1, "n_dots": 8, "has_alpha": True}
                preferred = before_publish(temporary, info) or preferred
                published = publish_unique_file(temporary, preferred)
                if type(self).calls == 1:
                    raise RuntimeError("simulated crash after publish")
                return {**info, "output_path": published}
            finally:
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    monkeypatch.setattr(cli, "Rip", CrashOnceRip)
    monkeypatch.setattr(sys, "argv", ["autorip", "--config", str(config), str(sample_png)])
    with pytest.raises(RuntimeError, match="simulated crash"):
        cli.main()
    assert len(list(output.glob("*.PRT"))) == 1

    # O próximo comando reconhece o hash exato, conclui sidecar e journal sem executar o RIP de novo.
    cli.main()
    assert CrashOnceRip.calls == 1
    assert len(list(output.glob("*.PRT"))) == 1
    assert len(list(output.glob("amostra_*.PRT.meta.json"))) == 1

    # Um sucesso já journalizado é ignorado na chamada repetida normal.
    cli.main()
    assert CrashOnceRip.calls == 1
    assert len(list(output.glob("*.PRT"))) == 1

    # A repetição intencional continua disponível e cria um novo nome, sem sobrescrever o anterior.
    monkeypatch.setattr(sys, "argv", ["autorip", "--config", str(config), "--force", str(sample_png)])
    cli.main()
    assert CrashOnceRip.calls == 2
    assert len(list(output.glob("*.PRT"))) == 2
