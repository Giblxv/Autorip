import json

import pytest

from tools.check_mobile_release_version import validate_mobile_release_version


def _fixture(root, *, package="0.2.0", lock="0.2.0", android="0.2.0", code=2, ios="0.2.0", build=2):
    (root / "mobile" / "android" / "app").mkdir(parents=True)
    (root / "mobile_ios").mkdir()
    (root / "mobile" / "package.json").write_text(
        json.dumps({"version": package}), encoding="utf-8"
    )
    (root / "mobile" / "package-lock.json").write_text(
        json.dumps({"version": lock, "packages": {"": {"version": lock}}}),
        encoding="utf-8",
    )
    (root / "mobile" / "android" / "app" / "build.gradle").write_text(
        f'versionCode {code}\nversionName "{android}"\n', encoding="utf-8"
    )
    (root / "mobile_ios" / "pubspec.yaml").write_text(
        f"version: {ios}+{build}\n", encoding="utf-8"
    )


def test_mobile_release_version_accepts_matching_platforms(tmp_path):
    _fixture(tmp_path)
    assert validate_mobile_release_version("mobile-v0.2.0", tmp_path) == "0.2.0"


@pytest.mark.parametrize(
    "field, value",
    [("package", "0.2.1"), ("lock", "0.2.1"), ("android", "0.2.1"), ("ios", "0.2.1")],
)
def test_mobile_release_version_rejects_platform_version_mismatch(tmp_path, field, value):
    _fixture(tmp_path, **{field: value})
    with pytest.raises(ValueError, match="divergentes"):
        validate_mobile_release_version("mobile-v0.2.0", tmp_path)


def test_mobile_release_version_requires_matching_build_numbers(tmp_path):
    _fixture(tmp_path, code=2, build=3)
    with pytest.raises(ValueError, match="versionCode Android=2, build iOS=3"):
        validate_mobile_release_version("mobile-v0.2.0", tmp_path)


def test_mobile_release_version_rejects_invalid_tag(tmp_path):
    _fixture(tmp_path)
    with pytest.raises(ValueError, match="mobile-vMAJOR.MINOR.PATCH"):
        validate_mobile_release_version("v0.2.0", tmp_path)
