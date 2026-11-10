"""Prova funcional real: RGBA/ICC de 90 MP versus referência sólida menor."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import warnings
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageCms
from autorip.config import Settings
from autorip.engine import Rip
from autorip.layout import inspect_image
from autorip.server import _load_thumbnail


def smoke(root, output):
    source = root / 'rgba-90mp.png'
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with source.open('wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')

        def chunk(kind, data):
            stream.write(struct.pack('>I', len(data)) + kind + data)
            stream.write(struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

        chunk(b'IHDR', struct.pack('>IIBBBBB', 10000, 9000, 8, 6, 0, 0, 0))
        chunk(b'iCCP', b'ICC Profile\0\0' + zlib.compress(profile))
        compressor = zlib.compressobj(level=1)
        row = b'\0' + bytes((20, 140, 210, 127)) * 10000
        for _ in range(9000):
            encoded = compressor.compress(row)
            if encoded:
                chunk(b'IDAT', encoded)
        chunk(b'IDAT', compressor.flush())
        chunk(b'IEND', b'')

    reference = root / 'reference.png'
    with Image.new('RGBA', (100, 90), (20, 140, 210, 127)) as image:
        image.save(reference, icc_profile=profile)
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    info = inspect_image(str(source))
    assert (info.width_px, info.height_px) == (10000, 9000)
    settings = Settings(dpi_x=72, dpi_y=72, margin_top_in=0, margin_bottom_in=0,
                        label_enabled=False, white_choke_mm=0, white_fill_holes_mm=0)
    rip = Rip(settings)
    results = []
    started = time.perf_counter()
    for path in (source, reference):
        prt_path = root / (path.stem + '.PRT')
        result = rip.process(str(path), str(prt_path), width_cm=2.54)
        actual_path = Path(result.pop('output_path'))
        results.append({'metadata': result, 'sha256': hashlib.sha256(actual_path.read_bytes()).hexdigest()})
    assert results[0] == results[1]
    preview = _load_thumbnail(source, (220, 220))
    try:
        assert preview.size == (220, 198)
        assert preview.getchannel('A').getextrema() == (127, 127)
    finally:
        preview.close()
    rss_file = Path('/proc/self/status')
    rss_line = (next(line for line in rss_file.read_text().splitlines() if line.startswith('VmHWM:'))
                if rss_file.is_file() else None)
    result = {'pixels': 90_000_000, 'source_size': [10000, 9000], 'mode': 'RGBA',
              'embedded_icc': 'sRGB', 'source_bytes': source.stat().st_size,
              'output_width_cm': 2.54, 'output_dpi': [72, 72], 'identical_reference_prt': True,
              'prt_sha256': results[0]['sha256'], 'metadata': results[0]['metadata'],
              'preview_size': [220, 198], 'preview_alpha': 127,
              'peak_rss_mib': int(rss_line.split()[1])/1024 if rss_line else None, 'elapsed_seconds': time.perf_counter()-started}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='autorip-large-input-') as folder:
        smoke(Path(folder), args.output.resolve())


if __name__ == '__main__':
    main()
