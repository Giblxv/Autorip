"""Motor do RIP: PNG -> (ICC) CMYK -> meio-tom estocastico 2 bits + branco automatico -> .PRT"""
import os
import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFont
from scipy import ndimage as ndi
from .config import Settings
from .prt import PrtWriter

Image.MAX_IMAGE_PIXELS = None
STRIP = 1024  # linhas de saida por bloco


def _blue_noise(h=256, w=256, sx=1.0, sy=None, seed=7):
    """Ruido azul aproximado (anisotropico para 720x2400): ruido branco passa-alta + ranking."""
    rng = np.random.default_rng(seed)
    sy = sy or sx * (2400 / 720)   # sigma em linhas ~3.33x o de colunas (grade anisotropica)
    n = rng.random((h, w))
    low = ndi.gaussian_filter(n, sigma=(sy, sx), mode="wrap")
    hp = n - low
    order = np.argsort(hp.ravel())
    r = np.empty(h * w)
    r[order] = (np.arange(h * w) + 0.5) / (h * w)
    return r.reshape(h, w)


class Rip:
    def __init__(self, s: Settings):
        self.s = s
        self.noise = _blue_noise(256, 256, sx=1.0)
        self.transform = None
        if s.icc_path and os.path.exists(s.icc_path):
            srgb = ImageCms.createProfile("sRGB")
            prof = ImageCms.getOpenProfile(s.icc_path)
            flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if s.black_point_comp else 0
            self.transform = ImageCms.buildTransform(
                srgb, prof, "RGB", "CMYK", renderingIntent=ImageCms.Intent(s.intent), flags=flags)

    # ---------- cor ----------
    def _to_cmyk(self, rgb: Image.Image) -> np.ndarray:
        if self.transform is not None:
            c = ImageCms.applyTransform(rgb, self.transform)
        else:
            c = rgb.convert("CMYK")
        a = np.asarray(c, dtype=np.float32) / 255.0          # (h,w,4) 1 = tinta cheia
        lim = [self.s.ink_limit.get(k, 100) / 100.0 for k in "CMYK"]
        return np.clip(a * np.array(lim, dtype=np.float32), 0, 1)

    def _halftone(self, v: np.ndarray, y0: int) -> np.ndarray:
        """v = volume de tinta (0..1, 1 = tudo gota grande) -> niveis {0,1,3}.
        Modelo medido nos .PRT reais (nivel 2 nunca usado): a gota pequena tem r~0,40 do volume da grande.
        v<=r : so gotas pequenas, cobertura v/r.  v>r : cobertura 100%, grandes na fracao (v-r)/(1-r).
        Conferido: branco 50% -> 16,7% de gotas grandes (real: 16,5%); 100% -> tudo nivel 3."""
        r = self.s.small_drop_ratio
        h, w = v.shape
        ny, nx = self.noise.shape
        t = self.noise[np.ix_((np.arange(h) + y0) % ny, np.arange(w) % nx)]
        small = (v / r) > t
        large = ((v - r) / (1.0 - r)) > t
        return np.where(large, 3, np.where(small, 1, 0)).astype(np.uint8)

    # ---------- branco ----------
    def _white_levels(self, alpha: np.ndarray) -> np.ndarray:
        s = self.s
        a = alpha
        # fecha furos de meio-tom / areas claras: cobertura = alpha >= limiar
        mask = a >= s.white_alpha_threshold
        fh = s.white_fill_holes_mm / 25.4
        ry, rx = int(round(fh * s.dpi_y)), int(round(fh * s.dpi_x))
        if rx > 0 and ry > 0:
            st = np.ones((2 * ry + 1, 2 * rx + 1), bool)
            pad = np.pad(mask, ((ry, ry), (rx, rx)))
            mask = ndi.binary_closing(pad, structure=st)[ry:-ry, rx:-rx]
        # recuo (choke) para o branco nao aparecer na borda
        cm = s.white_choke_mm / 25.4
        cy, cx = int(round(cm * s.dpi_y)), int(round(cm * s.dpi_x))
        if cx > 0 or cy > 0:
            mask = ndi.binary_erosion(mask, structure=np.ones((2 * cy + 1, 2 * cx + 1), bool))
        # niveis: borda (alpha parcial) = 1, miolo = 3
        # densidade 100% = tudo gota grande (3); abaixo disso: gotas pequenas + grandes esparsas
        dens = np.where(a >= 0.9, s.white_density, 0.5 * (a / 0.9) * s.white_density).astype(np.float32)
        dens = np.where(mask, dens, 0.0)
        return self._halftone(dens, 0)

    # ---------- etiqueta ----------
    def _make_labels(self, name, w_cm, h_cm, n_dots, top, art_rows, bot):
        s = self.s
        text = f"{name} {w_cm:.3f} x {h_cm:.3f} cm".replace(f"{w_cm:.3f}", f"{w_cm:.3f}".replace(".", ",")).replace(f"{h_cm:.3f}", f"{h_cm:.3f}".replace(".", ","))
        try: font = ImageFont.load_default(size=28)
        except TypeError: font = ImageFont.load_default()
        tmp = Image.new("L", (2400, 60), 0); d = ImageDraw.Draw(tmp)
        box = d.textbbox((0, 0), text, font=font); d.text((-box[0], -box[1]), text, fill=255, font=font)
        bw, bh = box[2] - box[0], box[3] - box[1]
        tmp = tmp.crop((0, 0, bw, bh))
        h_rows = min(int(0.30 / 2.54 * s.dpi_y), top - 8, bot - 8)               # texto com 3 mm de altura
        if h_rows < 20: return []
        w_dots = int(h_rows / s.dpi_y * 2.54 * (bw / bh) / 2.54 * s.dpi_x)
        if w_dots > n_dots: w_dots = n_dots; 
        lab = np.asarray(tmp.resize((max(1, w_dots), h_rows), Image.LANCZOS)) > 110
        if s.mirror: lab = lab[:, ::-1]
        x0 = (n_dots - lab.shape[1]) // 2
        return [((top - h_rows) // 2, x0, lab), (top + art_rows + (bot - h_rows) // 2, x0, lab)]

    # ---------- job ----------
    def process(self, png_path: str, out_path: str, width_cm: float = None, progress=None):
        s = self.s
        im = Image.open(png_path)
        im.load()
        has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
        im = im.convert("RGBA")
        dpi = im.info.get("dpi", (300, 300))[0] or 300
        w_cm = width_cm or (im.width / dpi * 2.54)
        n_dots = int(round(w_cm / 2.54 * s.dpi_x))
        art_rows = int(round((im.height / im.width) * w_cm / 2.54 * s.dpi_y))
        top = int(round(s.margin_top_in * s.dpi_y)); bot = int(round(s.margin_bottom_in * s.dpi_y))
        n_rows = top + art_rows + bot
        self._labels = self._make_labels(os.path.basename(png_path), w_cm, art_rows / s.dpi_y * 2.54, n_dots, top, art_rows, bot) if s.label_enabled else []
        tmp_path = out_path + ".part"
        wr = PrtWriter(tmp_path, s.dpi_x, s.dpi_y, n_rows, n_dots)
        halo = 64
        try:
            y = 0
            while y < n_rows:
                y1 = min(n_rows, y + STRIP)
                a0, a1 = max(0, y - halo), min(n_rows, y1 + halo)       # com halo para morfologia
                planes_full = self._render(im, a0, a1, top, art_rows, n_dots)
                o = y - a0
                blk = [p[o:o + (y1 - y)] for p in planes_full]
                wr.write_block(blk)
                y = y1
                if progress:
                    progress(y / n_rows)
        except BaseException:
            wr.f.close()
            if os.path.exists(tmp_path): os.remove(tmp_path)
            raise
        wr.close()
        os.replace(tmp_path, out_path)
        return dict(n_rows=n_rows, n_dots=n_dots, width_cm=w_cm,
                    height_cm=art_rows / s.dpi_y * 2.54, has_alpha=has_alpha)

    def _render(self, im, a0, a1, top, art_rows, n_dots):
        s = self.s
        h = a1 - a0
        planes = [np.zeros((h, n_dots), np.uint8) for _ in range(12)]
        r0, r1 = max(a0, top), min(a1, top + art_rows)
        if r1 > r0:
            sy = im.height / art_rows
            box = (0, (r0 - top) * sy, im.width, (r1 - top) * sy)
            strip = im.resize((n_dots, r1 - r0), Image.LANCZOS, box=box)
            if s.mirror:
                strip = strip.transpose(Image.FLIP_LEFT_RIGHT)
            arr = np.asarray(strip)
            alpha = arr[..., 3].astype(np.float32) / 255.0
            rgb = Image.fromarray(arr[..., :3], "RGB")
            cmyk = self._to_cmyk(rgb) * alpha[..., None]          # tinta so onde ha arte
            o = r0 - a0
            idx = {"C": 0, "M": 1, "Y": 2, "K": 3}            # ordem do array CMYK do Pillow
            for pl, name in enumerate(s.channel_order):          # plano -> tinta
                planes[pl][o:o + (r1 - r0)] = self._halftone(cmyk[..., idx[name]], r0)
            if s.white_enabled:
                full_alpha = np.zeros((h, n_dots), np.float32)
                full_alpha[o:o + (r1 - r0)] = alpha
                lvl = self._white_levels(full_alpha)
                for pidx in s.white_planes:
                    planes[pidx] = lvl
        for (ly, lx, lab) in getattr(self, "_labels", []):                 # etiqueta em K (plano 0)
            ys, ye = max(ly, a0), min(ly + lab.shape[0], a1)
            if ye > ys:
                seg = lab[ys - ly:ye - ly]
                dst = planes[s.channel_order.index("K")][ys - a0:ye - a0, lx:lx + lab.shape[1]]
                dst[seg] = 3
        return planes
