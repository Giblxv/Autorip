"""RIP com normalizacao CMYK direta: RGBA, entradas grandes e controle RGB.

python benchmarks/benchmark_cmyk_direct.py --baseline-ref v0.8.39 --pairs 7 --icc /caminho/cmyk.icc --output /tmp/cmyk.json
"""
from PIL import Image
from benchmark_identity_strips import main as benchmark
from benchmark_opaque_lut import fixtures as pattern_fixtures


def fixtures(root, icc=None):
    patterns = pattern_fixtures(root, icc)
    alpha = next(case for case in patterns if case['name'] == 'rgba_control')
    rgb = next(case for case in patterns if case['name'] == 'rgb_scaled')
    with Image.open(alpha['path']) as image:
        large = image.resize((4096, 3072), Image.LANCZOS)
        large.save(root / 'large-rgba.png')
        large.close()
    cases = [dict(alpha, name='rgba_scaled', settings=alpha['settings'] | dict(white_enabled=False)),
             dict(alpha, name='rgba_scaled_white'),
             dict(alpha, name='rgba_wide', width_cm=4000 / 720 * 2.54,
                  settings=alpha['settings'] | dict(dpi_x=720, dpi_y=720, white_enabled=False)),
             dict(alpha, name='rgba_wide_white', width_cm=4000 / 720 * 2.54,
                  settings=alpha['settings'] | dict(dpi_x=720, dpi_y=720)),
             dict(alpha, name='rgba_identity', width_cm=768 / 300 * 2.54,
                  settings=alpha['settings'] | dict(dpi_x=300, dpi_y=300, white_enabled=False)),
             dict(alpha, name='rgba_large_source', path=str(root / 'large-rgba.png')),
             next(case for case in patterns if case['name'] == 'small_rgb_control'),
             dict(rgb, name='large_rgb_control')]
    if icc is not None:
        cases.append(dict(alpha, name='rgba_icc_white', settings=alpha['settings'] | dict(icc_path=str(icc))))
    return cases


if __name__ == '__main__':
    benchmark(fixtures, __doc__)
