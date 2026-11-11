"""Gera os dois controles TIFF adicionais a partir das fontes de 90 MP."""
import argparse
import hashlib
import json
from pathlib import Path

from benchmark_large_artwork import Image, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads((args.fixtures / 'cases.json').read_text())
    rgb = next(c for c in cases if c['name'] == 'rgb_icc_90mp')
    rgba = next(c for c in cases if c['name'] == 'rgba_icc_90mp')
    assert sha(rgba['path']) == rgba['source_sha256']
    args.output.mkdir(parents=True, exist_ok=True)
    with Image.open(rgba['path']) as source:
        image = source.crop((0, 0, 6000, 5000))
    try:
        profile = image.info['icc_profile']
        generated = [rgb]
        for name, compression, orientation in [
            ('deflate_rgba_icc_30mp', 'tiff_adobe_deflate', 1),
            ('oriented_tiff_rgba_icc_30mp', 'raw', 6),
        ]:
            path = (args.output / (name + '.tiff')).resolve()
            exif = Image.Exif(); exif[274] = orientation
            image.save(path, compression=compression, icc_profile=profile,
                       dpi=(100, 200), exif=exif)
            generated.append(dict(name=name, path=str(path), mode='RGBA',
                source_size=[6000, 5000], source_sha256=sha(path),
                source_bytes=path.stat().st_size,
                profile_sha256=hashlib.sha256(profile).hexdigest(),
                width_cm=5.08, phases=['job'], settings=rgb['settings']))
        (args.output / 'cases.json').write_text(json.dumps(generated, indent=2) + '\n')
    finally:
        image.close()


if __name__ == '__main__':
    main()
