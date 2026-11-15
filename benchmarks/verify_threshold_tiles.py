"""Confere 30 artes distintas, byte a byte, contra uma revisao do motor."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
from autorip import engine
from autorip.config import Settings
from benchmark_main_refinements import baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profile = ROOT / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    report = []
    with tempfile.TemporaryDirectory(prefix='autorip-exact-30-') as folder:
        root = Path(folder)
        old = baseline(args.baseline_ref, root)
        for index in range(30):
            width, height = 257 + index * 3, 273 + index * 5
            pixels = np.random.default_rng(8700 + index).integers(0, 256, (height, width, 4), dtype=np.uint8)
            image = Image.fromarray(pixels)
            if index % 3 == 0:
                converted = image.convert('RGB')
                image.close()
                image = converted
            suffix = '.tiff' if index % 2 else '.png'
            source = root / f'input-{index}{suffix}'
            image.save(source)
            image.close()
            settings = Settings(dpi_x=300, dpi_y=300, label_enabled=index % 5 == 0,
                                white_enabled=index % 4 != 0, white_density=.45 if index % 2 else 1.,
                                small_drop_ratio=[.05, .4, .95][index % 3], mirror=bool(index % 2),
                                icc_path=str(profile) if index % 4 == 0 else '',
                                ink_limit=dict(C=35.5, M=0, Y=88.25, K=100),
                                channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7],
                                margin_top_in=.02, margin_bottom_in=.02)
            results = []
            workers = 1 if index % 2 else 4
            for side, module in enumerate((old, engine)):
                original_workers = module._available_cpu_count
                try:
                    module._available_cpu_count = lambda: workers
                    rip = module.Rip(settings)
                    info = rip.process(str(source), str(root / f'{side}.PRT'), width_cm=width / 300 * 2.54)
                    output = Path(info.pop('output_path'))
                    data = output.read_bytes()
                    output.unlink()
                    results.append((data, info))
                finally:
                    module._available_cpu_count = original_workers
            assert results[0] == results[1], index
            report.append(dict(case=index, seed=8700 + index, size=[width, height],
                               format=suffix, workers=workers,
                               input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                               output_sha256=hashlib.sha256(results[0][0]).hexdigest(),
                               metadata=results[0][1], equal=True))
    assert len({case['output_sha256'] for case in report}) == 30
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('30 entradas distintas: PRTs byte a byte e metadados identicos')


if __name__ == '__main__':
    main()
