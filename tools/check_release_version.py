"""Impede publicar uma release cuja tag difere da versão Python/Inno Setup."""
import ast
import re
import sys
from pathlib import Path

VERSION_RE = re.compile(r"v?(\d+\.\d+\.\d+)\Z")
INNO_RE = re.compile(r'(?m)^#define AppVersion "([^"]+)"\s*$')


def release_versions(root: Path):
    source = ast.parse((root / "autorip" / "__init__.py").read_text(encoding="utf-8"))
    python_version = None
    for node in source.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                python_version = node.value.value
    inno_content = (root / "installer.iss").read_text(encoding="utf-8")
    match = INNO_RE.search(inno_content)
    if python_version is None or match is None:
        raise ValueError("Versão ausente no Python ou no instalador Inno Setup.")
    return python_version, match.group(1)


def validate_release_tag(tag: str, root: Path):
    match = VERSION_RE.fullmatch(tag)
    if not match:
        raise ValueError("Tag precisa ter formato vMAJOR.MINOR.PATCH (ex.: v0.8.7).")
    expected = match.group(1)
    python_version, inno_version = release_versions(root)
    if (python_version, inno_version) != (expected, expected):
        raise ValueError(
            f"Versões divergentes: tag={expected}, Python={python_version}, "
            f"Inno Setup={inno_version}. Atualize ambos antes da release."
        )
    return expected


if __name__ == "__main__":
    try:
        checked = validate_release_tag(sys.argv[1] if len(sys.argv) == 2 else "",
                                      Path(__file__).resolve().parents[1])
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"Release bloqueada: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Versão da release validada: {checked}")
