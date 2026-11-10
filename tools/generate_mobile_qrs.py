"""Gera os QR codes móveis exibidos no painel e no instalador Windows."""
from io import BytesIO
from pathlib import Path

import segno
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "installer_assets"
UI = ROOT / "autorip" / "ui"
LINKS = {
    "mobile-android": "https://github.com/Giblxv/AutoRIP/releases/download/mobile-v0.1.0/app-debug.apk",
    "mobile-ios-guide": "https://github.com/Giblxv/AutoRIP/blob/main/docs/GUIA-APPS-MOVEIS.md",
}


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    UI.mkdir(parents=True, exist_ok=True)
    for stem, url in LINKS.items():
        png = BytesIO()
        segno.make_qr(url, error="M").save(png, kind="png", scale=4, border=4)
        png.seek(0)
        with Image.open(png) as image:
            rgb = image.convert("RGB")
            rgb.save(ASSETS / f"{stem}.bmp", format="BMP")
            rgb.save(UI / f"{stem}-qr.png", format="PNG", optimize=True)
        print(f"Gerado QR {stem} -> {url}")


if __name__ == "__main__":
    main()
