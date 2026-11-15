"""Compara RIP RGB opaco com tabelas/ranks exatos e controles de fallback.

python benchmarks/benchmark_opaque_lut.py --baseline-ref v0.8.35 --pairs 7 --icc /caminho/cmyk.icc --output /tmp/opaque.json
"""
import numpy as np
from PIL import Image
from benchmark_identity_strips import main as benchmark


def fixtures(root, icc=None):
    yy, xx = np.indices((512, 768))
    data = np.stack([(xx * 3 + yy) % 256, (xx + yy * 7) % 256,
                     (xx * 11 + yy) % 256, (xx * 5 + yy * 3) % 256], axis=-1).astype(np.uint8)
    rgba = Image.fromarray(data)
    rgba.save(root / 'rgba.png')
    rgb = rgba.convert('RGB')
    rgb.save(root / 'rgb.png')
    for name, size in [('square', (256, 256)), ('identity', (1025, 2048)), ('large', (4096, 3072))]:
        image = rgb.resize(size, Image.LANCZOS)
        image.save(root / (name + ('.jpg' if name == 'large' else '.png')))
        image.close()
    rgba.close()
    rgb.close()
    common = dict(label_enabled=False, margin_top_in=.02, margin_bottom_in=.02,
                  white_enabled=False)
    def case(name, file, width, **settings):
        return dict(name=name, path=str(root / file), width_cm=width,
                    settings=common | settings)
    cases = [case('small_rgb_control', 'rgb.png', 1.27),
             case('rgb_scaled', 'rgb.png', 5.08),
             case('rgb_limits', 'rgb.png', 5.08, ink_limit=dict(C=35.5, M=0, Y=88.25, K=100)),
             case('rgb_wide', 'square.png', 4000 / 720 * 2.54, dpi_x=720, dpi_y=720),
             case('rgb_identity', 'identity.png', 1025 / 300 * 2.54, dpi_x=300, dpi_y=300),
             case('large_jpeg', 'large.jpg', 5.08),
             case('rgba_control', 'rgba.png', 5.08, white_enabled=True)]
    if icc is not None:
        cases.append(case('rgb_icc_white', 'rgb.png', 5.08, white_enabled=True, icc_path=str(icc)))
    return cases


if __name__ == '__main__':
    benchmark(fixtures, __doc__)
