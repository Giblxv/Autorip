"""RIP completo com alfa booleano para branco opaco e controles de fallback."""
from benchmark_identity_strips import main as benchmark
from benchmark_opaque_lut import fixtures as opaque_fixtures


def fixtures(root, icc=None):
    originals = opaque_fixtures(root, icc)
    cases = []
    for source in originals:
        if source['name'] in {'rgb_scaled', 'rgb_wide', 'rgb_identity', 'small_rgb_control'}:
            cases.append(dict(source, name=source['name'] + '_white',
                              settings=source['settings'] | dict(white_enabled=True)))
            if source['name'] in {'rgb_scaled', 'rgb_wide'}:
                cases.append(dict(source, name=source['name'] + '_white_45',
                                  settings=source['settings'] | dict(white_enabled=True, white_density=.45)))
        elif source['name'] in {'rgb_icc_white', 'rgba_control'}:
            cases.append(source)
    source = next(case for case in originals if case['name'] == 'rgb_scaled')
    cases += [dict(source, name='rgb_no_white_control'),
              dict(source, name='zero_alpha_threshold_control',
                   settings=source['settings'] | dict(white_enabled=True, white_alpha_threshold=0))]
    return cases


if __name__ == '__main__':
    benchmark(fixtures, __doc__)
