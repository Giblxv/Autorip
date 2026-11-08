"""Motor do RIP: PNG -> (ICC) CMYK -> meio-tom estocastico 2 bits + branco automatico -> .PRT"""
import os
import io
import shutil
import tempfile
import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps
from scipy import ndimage as ndi
from .config import Settings
from .prt import PrtWriter, plane_bytes_for, HEADER_SIZE
from .paths import publish_unique_file

MAX_INPUT_PIXELS = 80_000_000
MIN_FREE_DISK_BYTES = 128 * 1024 * 1024  # reserva para logs, journal e sistema
STRIP = 512  # reduz o pico de memoria em folhas largas
MAX_STRIP_MEMORY_BYTES = 512 * 1024 * 1024
_BYTES_PER_RENDER_PIXEL = 48  # planos, alpha, CMYK float e buffers temporários


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
        self.s = s.validate()
        self.noise = _blue_noise(256, 256, sx=1.0, sy=s.dpi_y / s.dpi_x)
        self.transform = None
        self.icc_error = None
        if s.icc_path:
            try:
                if not os.path.isfile(s.icc_path):
                    raise FileNotFoundError(s.icc_path)
                srgb = ImageCms.createProfile("sRGB")
                prof = ImageCms.getOpenProfile(s.icc_path)
                flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if s.black_point_comp else 0
                self.transform = ImageCms.buildTransform(
                    srgb, prof, "RGB", "CMYK", renderingIntent=ImageCms.Intent(s.intent), flags=flags)
            except Exception as exc:
                self.icc_error = f"Perfil ICC indisponivel ou invalido: {exc}"

    def _source_rgba(self, source: Image.Image) -> Image.Image:
        embedded = source.info.get("icc_profile")
        if not embedded:
            return source.convert("RGBA")
        try:
            profile = ImageCms.ImageCmsProfile(io.BytesIO(embedded))
            if source.mode in ("RGBA", "P", "PA"):
                color = source.convert("RGB")
            elif source.mode == "LA":
                color = source.getchannel("L")
            else:
                color = source
            flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if self.s.black_point_comp else 0
            rgb = ImageCms.profileToProfile(color, profile, ImageCms.createProfile("sRGB"),
                                           outputMode="RGB", renderingIntent=self.s.intent, flags=flags)
            rgba = rgb.convert("RGBA")
            if source.mode in ("RGBA", "LA", "PA") or "transparency" in source.info:
                rgba.putalpha(source.convert("RGBA").getchannel("A"))
            return rgba
        except Exception as exc:
            raise ValueError(f"Perfil ICC de entrada indisponivel ou invalido: {exc}") from exc

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
    def _white_levels(self, alpha: np.ndarray, y0: int = 0) -> np.ndarray:
        s = self.s
        a = alpha
        # fecha furos de meio-tom / areas claras: cobertura = alpha >= limiar
        original_mask = a >= s.white_alpha_threshold
        mask = original_mask
        fh = s.white_fill_holes_mm / 25.4
        ry, rx = int(round(fh * s.dpi_y)), int(round(fh * s.dpi_x))
        if rx > 0 or ry > 0:
            st = np.ones((2 * ry + 1, 2 * rx + 1), bool)
            pad = np.pad(mask, ((ry, ry), (rx, rx)))
            mask = ndi.binary_closing(pad, structure=st)[ry:ry + a.shape[0], rx:rx + a.shape[1]]
        # recuo (choke) para o branco nao aparecer na borda
        cm = s.white_choke_mm / 25.4
        cy, cx = int(round(cm * s.dpi_y)), int(round(cm * s.dpi_x))
        if cx > 0 or cy > 0:
            mask = ndi.binary_erosion(mask, structure=np.ones((2 * cy + 1, 2 * cx + 1), bool))
        # niveis: borda (alpha parcial) = 1, miolo = 3
        # densidade 100% = tudo gota grande (3); abaixo disso: gotas pequenas + grandes esparsas
        dens = np.where(a >= 0.9, s.white_density, 0.5 * (a / 0.9) * s.white_density).astype(np.float32)
        # Pixels transparentes adicionados pelo fechamento sao furos preenchidos:
        # sem esta atribuicao, a mascara fechava, mas a densidade continuava zero.
        dens[mask & ~original_mask] = s.white_density
        dens = np.where(mask, dens, 0.0)
        return self._halftone(dens, y0)

    # ---------- etiqueta ----------
    def _make_labels(self, name, w_cm, h_cm, n_dots, top, art_rows, bot):
        s = self.s
        text = f"{name} {w_cm:.3f} x {h_cm:.3f} cm".replace(f"{w_cm:.3f}", f"{w_cm:.3f}".replace(".", ",")).replace(f"{h_cm:.3f}", f"{h_cm:.3f}".replace(".", ","))
        try: font = ImageFont.load_default(size=28)
        except TypeError: font = ImageFont.load_default()
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        box = probe.textbbox((0, 0), text, font=font)
        bw, bh = box[2] - box[0], box[3] - box[1]
        tmp = Image.new("L", (max(1, bw), max(1, bh)), 0)
        ImageDraw.Draw(tmp).text((-box[0], -box[1]), text, fill=255, font=font)
        h_rows = min(int(0.30 / 2.54 * s.dpi_y), top - 8, bot - 8)               # texto com 3 mm de altura
        if h_rows < 20: return []
        w_dots = int(h_rows / s.dpi_y * 2.54 * (bw / bh) / 2.54 * s.dpi_x)
        if w_dots > n_dots: w_dots = n_dots; 
        lab = np.asarray(tmp.resize((max(1, w_dots), h_rows), Image.LANCZOS)) > 110
        if s.mirror: lab = lab[:, ::-1]
        x0 = (n_dots - lab.shape[1]) // 2
        return [((top - h_rows) // 2, x0, lab), (top + art_rows + (bot - h_rows) // 2, x0, lab)]

    # ---------- job ----------
    def process(self, png_path: str, out_path: str, width_cm: float = None, progress=None, before_publish=None):
        s = self.s
        if self.icc_error:
            raise RuntimeError(self.icc_error)
        out_path = os.path.realpath(out_path)
        out_dir = os.path.dirname(out_path)
        os.makedirs(out_dir, exist_ok=True)
        with Image.open(png_path) as opened:
            # EXIF transpose decodifica os pixels; valide o cabecalho antes disso.
            if opened.width * opened.height > MAX_INPUT_PIXELS:
                raise ValueError(f"Imagem excede o limite de {MAX_INPUT_PIXELS:,} pixels; reduza a arte antes do RIP.")
            if opened.width <= 0 or opened.height <= 0:
                raise ValueError("A imagem precisa ter largura e altura maiores que zero.")
            orientation = opened.getexif().get(274, 1)
            source = ImageOps.exif_transpose(opened)
            has_alpha = source.mode in ("RGBA", "LA", "PA") or "transparency" in source.info
            source_dpi = source.info.get("dpi", (300, 300))
            source_dpi_x, source_dpi_y = source_dpi[0] or 300, source_dpi[1] or 300
            if orientation in (5, 6, 7, 8):
                source_dpi_x, source_dpi_y = source_dpi_y, source_dpi_x
            source.load()
            im = self._source_rgba(source)
        w_cm = width_cm if width_cm is not None else (im.width / source_dpi_x * 2.54)
        if not np.isfinite(w_cm) or w_cm <= 0:
            raise ValueError("A largura de impressão precisa ser um número positivo.")
        n_dots = int(round(w_cm / 2.54 * s.dpi_x))
        physical_ratio = (im.height / source_dpi_y) / (im.width / source_dpi_x)
        art_rows = int(round(physical_ratio * w_cm / 2.54 * s.dpi_y))
        if n_dots <= 0 or art_rows <= 0:
            raise ValueError("A largura ou a resolucao escolhida gera uma arte sem pixels de saida; aumente as medidas.")
        top = int(round(s.margin_top_in * s.dpi_y)); bot = int(round(s.margin_bottom_in * s.dpi_y))
        n_rows = top + art_rows + bot
        if n_rows <= 0 or n_rows >= 2**32 or n_dots >= 2**32:
            raise ValueError("As dimensoes de saida excedem o limite representavel pelo formato PRT.")
        labels = self._make_labels(os.path.basename(png_path), w_cm, art_rows / s.dpi_y * 2.54, n_dots, top, art_rows, bot) if s.label_enabled else []
        estimated_bytes = HEADER_SIZE + n_rows * 12 * plane_bytes_for(n_dots)
        free_bytes = shutil.disk_usage(out_dir).free
        if estimated_bytes + MIN_FREE_DISK_BYTES > free_bytes:
            raise ValueError(f"Espaco insuficiente: o PRT deve ocupar aproximadamente {estimated_bytes / 1024**3:.2f} GiB, alem de 128 MiB de reserva livre.")
        fill_rows = int(round(s.white_fill_holes_mm / 25.4 * s.dpi_y)) if s.white_enabled else 0
        choke_rows = int(round(s.white_choke_mm / 25.4 * s.dpi_y)) if s.white_enabled else 0
        halo = 2 * fill_rows + choke_rows + 2
        available_rows = MAX_STRIP_MEMORY_BYTES // max(1, n_dots * _BYTES_PER_RENDER_PIXEL) - 2 * halo
        if available_rows < 1:
            raise ValueError("A largura/DPI exigem mais memória do que o limite seguro de processamento por tira.")
        strip_rows = max(1, min(STRIP, int(available_rows)))
        fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(out_path)}.", suffix=".part", dir=out_dir)
        os.close(fd)
        wr = None
        try:
            wr = PrtWriter(tmp_path, s.dpi_x, s.dpi_y, n_rows, n_dots)
            y = 0
            while y < n_rows:
                y1 = min(n_rows, y + strip_rows)
                a0, a1 = max(0, y - halo), min(n_rows, y1 + halo)       # com halo para morfologia
                planes_full = self._render(im, a0, a1, top, art_rows, n_dots, labels)
                o = y - a0
                blk = [p[o:o + (y1 - y)] for p in planes_full]
                wr.write_block(blk)
                y = y1
                if progress:
                    progress(y / n_rows)
            wr.close()
            result = dict(n_rows=n_rows, n_dots=n_dots, width_cm=w_cm,
                          height_cm=art_rows / s.dpi_y * 2.54, dpi_x=s.dpi_x,
                          dpi_y=s.dpi_y, has_alpha=has_alpha)
            if before_publish:
                before_publish(tmp_path, dict(result))
            out_path = publish_unique_file(tmp_path, out_path)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        except BaseException:
            if wr is not None and not wr.f.closed:
                wr.f.close()
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
        result["output_path"] = out_path
        return result

    def _render(self, im, a0, a1, top, art_rows, n_dots, labels):
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
                lvl = self._white_levels(full_alpha, a0)
                for pidx in s.white_planes:
                    planes[pidx] = lvl
        for (ly, lx, lab) in labels:                 # etiqueta em K (plano 0)
            ys, ye = max(ly, a0), min(ly + lab.shape[0], a1)
            if ye > ys:
                seg = lab[ys - ly:ye - ly]
                dst = planes[s.channel_order.index("K")][ys - a0:ye - a0, lx:lx + lab.shape[1]]
                dst[seg] = 3
        return planes
