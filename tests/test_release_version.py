from pathlib import Path

import pytest

from tools.check_release_version import validate_release_tag, release_versions


def test_tag_versao_repo_coincide_com_python_e_instalador():
    root = Path(__file__).resolve().parents[1]
    app, installer = release_versions(root)
    assert app == installer
    assert validate_release_tag("v" + app, root) == app


def test_release_recusa_tag_divergente_do_instalador(tmp_path):
    package = tmp_path / "autorip"
    package.mkdir()
    (package / "__init__.py").write_text('__version__ = "0.9.0"\n')
    (tmp_path / "installer.iss").write_text('#define AppVersion "0.8.7"\n')
    with pytest.raises(ValueError, match="divergentes"):
        validate_release_tag("v0.9.0", tmp_path)
    (tmp_path / "installer.iss").write_text('#define AppVersion "0.9.0"\n')
    assert validate_release_tag("v0.9.0", tmp_path) == "0.9.0"


@pytest.mark.parametrize("tag", [
    "0.8", "0.8.7", "v01.2.3", "v1.02.3", "v1.2.03",
    "v1.2.3-rc.1", "v1.2.3+build.4", "../v1.2.3", "v1.2.3/evil", "v١.2.3", "",
])
def test_release_recusa_tags_fora_do_padrao(tmp_path, tag):
    with pytest.raises(ValueError, match="Tag"):
        validate_release_tag(tag, tmp_path)
