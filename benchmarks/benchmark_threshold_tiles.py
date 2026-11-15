"""Compara limiares compactos exatos em RGBA/branco e controles RGB.

python benchmarks/benchmark_threshold_tiles.py --baseline-ref v0.8.36 --pairs 7 --icc /caminho/cmyk.icc --output /tmp/thresholds.json
"""
from benchmark_identity_strips import main as benchmark, fixtures as identity_fixtures
from benchmark_opaque_lut import fixtures as opaque_fixtures


def fixtures(root, icc=None):
    identity = identity_fixtures(root, icc)
    opaque = opaque_fixtures(root, icc)
    cases = [case for case in identity if case['name'] in {
        'rgba_one_strip', 'rgba_tall', 'rgba_tall_white', 'rgba_tall_output_icc'
    }] + [case for case in opaque if case['name'] in {
        'rgb_scaled', 'rgb_icc_white', 'rgba_control', 'small_rgb_control'
    }]
    cases.append(dict(name='rgba_wide', path=str(root / 'rgba.png'),
                      width_cm=4000 / 720 * 2.54,
                      settings=dict(dpi_x=720, dpi_y=720, white_enabled=True,
                                    label_enabled=False, margin_top_in=.02, margin_bottom_in=.02)))
    return cases


if __name__ == '__main__':
    benchmark(fixtures, __doc__)
