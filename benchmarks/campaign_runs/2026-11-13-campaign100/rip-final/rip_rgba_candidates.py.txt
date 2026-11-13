"""Hipóteses específicas de RGBA e a bateria ampla existente, somente para ensaio."""
from rip_candidates import change
from rip_wide_candidates import CANDIDATES as WIDE


def rgba_no_cache(bundle):
    if '        if mode == "RGBA":\n            flags |= ImageCms.Flags.NOCACHE\n' in bundle['engine']:
        return None
    before = '        output_mode = "RGBA" if mode == "RGBA" else "RGB"'
    if before not in bundle['engine']:
        before = '        profile = ImageCms.ImageCmsProfile(io.BytesIO(embedded))'
    after = '''        if mode == "RGBA":
            flags |= ImageCms.Flags.NOCACHE
''' + before
    return change(bundle, 'engine', before, after)


def rgba_copied_in_place(bundle):
    before = '                return ImageCms.applyTransform(source, transform)'
    after = '''                copied = source.copy()
                try:
                    ImageCms.applyTransform(copied, transform, inPlace=True)
                except Exception:
                    copied.close()
                    raise
                return copied'''
    return change(bundle, 'engine', before, after)


CANDIDATES = [
    ('rgba-no-pixel-cache', 'Desativar cache nativo em RGBA, com controles de cores planas e variadas', rgba_no_cache),
    ('rgba-copied-in-place', 'Transformar uma cópia RGBA in-place para comparar localidade e cópia', rgba_copied_in_place),
    *WIDE,
]
