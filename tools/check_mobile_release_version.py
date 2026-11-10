"""Valida que a tag móvel corresponde às versões Android, npm e Flutter iOS."""

import json
import re
import sys
from pathlib import Path

TAG_RE = re.compile(r"mobile-v(\d+\.\d+\.\d+)\Z")
ANDROID_NAME_RE = re.compile(r'(?m)^\s*versionName\s+"([^"]+)"\s*$')
ANDROID_CODE_RE = re.compile(r"(?m)^\s*versionCode\s+(\d+)\s*$")
IOS_VERSION_RE = re.compile(r"(?m)^version:\s*(\d+\.\d+\.\d+)\+(\d+)\s*$")


def validate_mobile_release_version(tag: str, root: Path) -> str:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError("Tag precisa ter formato mobile-vMAJOR.MINOR.PATCH.")
    expected = match.group(1)

    package = json.loads((root / "mobile" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "mobile" / "package-lock.json").read_text(encoding="utf-8"))
    gradle = (root / "mobile" / "android" / "app" / "build.gradle").read_text(encoding="utf-8")
    pubspec = (root / "mobile_ios" / "pubspec.yaml").read_text(encoding="utf-8")

    android_name = ANDROID_NAME_RE.search(gradle)
    android_code = ANDROID_CODE_RE.search(gradle)
    ios_version = IOS_VERSION_RE.search(pubspec)
    lock_root = lock.get("packages", {}).get("", {})
    if not android_name or not android_code or not ios_version:
        raise ValueError("Versão Android ou iOS ausente/inválida.")

    versions = {
        "tag": expected,
        "package.json": package.get("version"),
        "package-lock.json": lock.get("version"),
        "package-lock root": lock_root.get("version"),
        "Android versionName": android_name.group(1),
        "iOS version": ios_version.group(1),
    }
    mismatches = [f"{name}={value}" for name, value in versions.items() if value != expected]
    android_code_value = int(android_code.group(1))
    ios_build_value = int(ios_version.group(2))
    if android_code_value <= 0 or ios_build_value <= 0 or android_code_value != ios_build_value:
        mismatches.append(f"versionCode Android={android_code_value}, build iOS={ios_build_value}")
    if mismatches:
        raise ValueError("Versões móveis divergentes: " + ", ".join(mismatches))
    return expected


if __name__ == "__main__":
    try:
        checked = validate_mobile_release_version(
            sys.argv[1] if len(sys.argv) == 2 else "", Path(__file__).resolve().parents[1]
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Release móvel bloqueada: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Versão móvel validada: {checked}")
