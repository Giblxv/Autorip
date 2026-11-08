import json
import os
import stat

import pytest

from autorip.config import Settings


def test_settings_rejeitam_resolucao_fora_do_intervalo():
    with pytest.raises(ValueError, match="dpi_x"):
        Settings(dpi_x=20).validate()
    with pytest.raises(ValueError, match="white_density"):
        Settings(white_density=1.5).validate()


def test_settings_rejeitam_valores_json_aninhados_malformados():
    with pytest.raises(ValueError, match="channel_order"):
        Settings(channel_order=[["K"], "C", "M", "Y"]).validate()


def test_endpoints_de_integracao_exigem_tls_fora_de_loopback():
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(webhook_url="http://example.invalid/hook").validate()
    Settings(webhook_url="http://127.0.0.1:9999/hook").validate()
    with pytest.raises(ValueError, match="allowlist"):
        Settings(anthropic_base="https://api.anthropic.com.attacker.invalid").validate()


def test_pastas_de_trabalho_nao_podem_ser_iguais_ou_sobrepostas(tmp_path):
    same = str(tmp_path / "work")
    with pytest.raises(ValueError, match="hot_folder e done_folder"):
        Settings(hot_folder=same, done_folder=same).validate()
    with pytest.raises(ValueError, match="hot_folder e error_folder"):
        Settings(hot_folder=same, error_folder=os.path.join(same, "erros")).validate()
    real = tmp_path / "real"
    alias = tmp_path / "alias"
    real.mkdir()
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError, match="hot_folder e done_folder"):
        Settings(hot_folder=str(real), done_folder=str(alias)).validate()


def test_load_ignora_chaves_json_que_nao_sao_campos_dataclass(tmp_path):
    path = tmp_path / "autorip.json"
    path.write_text(json.dumps({"dpi_x": 300, "__dict__": {"evil": True}, "save": "overridden"}), encoding="utf-8")
    settings = Settings.load(path)
    assert settings.dpi_x == 300
    assert callable(settings.save)
    assert not hasattr(settings, "evil")


def test_save_e_atomico_e_privado_em_posix(tmp_path):
    path = tmp_path / "autorip.json"
    settings = Settings()
    settings.save(path)
    assert Settings.load(path).dpi_x == settings.dpi_x
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_canonicalize_folders_resolve_symlink_antes_de_parent(tmp_path):
    real_parent = tmp_path / "real"
    symlink_target = tmp_path / "target" / "parent"
    real_parent.mkdir()
    symlink_target.mkdir(parents=True)
    link = real_parent / "link"
    try:
        link.symlink_to(symlink_target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink indisponivel neste ambiente")
    raw = link / ".." / "hot"
    expected = os.path.realpath(str(raw))
    if expected == os.path.realpath(os.path.abspath(str(raw))):
        pytest.skip("Plataforma normaliza segmentos .. antes de resolver o symlink")

    settings = Settings(
        hot_folder=str(raw),
        output_folder=str(tmp_path / "out"),
        printed_folder=str(tmp_path / "printed"),
        done_folder=str(tmp_path / "done"),
        error_folder=str(tmp_path / "errors"),
    )
    settings.canonicalize_folders()
    settings.validate()
    assert settings.hot_folder == expected

    from autorip.paths import ProcessLock
    lock = ProcessLock(os.path.join(str(raw), ".autorip.output.lock"))
    assert lock.path == os.path.join(expected, ".autorip.output.lock")
