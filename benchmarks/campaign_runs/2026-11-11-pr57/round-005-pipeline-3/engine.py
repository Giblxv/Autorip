"""Motor do RIP: PNG -> (ICC) CMYK -> meio-tom estocastico 2 bits + branco automatico -> .PRT"""
import math
import os
import io
import shutil
import tempfile
import threading
from collections import OrderedDict
import numpy as np
from PIL import ImageCms, ImageDraw, ImageFont, ImageOps
from .imaging import Image
from scipy import ndimage as ndi
from .config import Settings
from .prt import PrtWriter, plane_bytes_for, HEADER_SIZE
from .paths import publish_unique_file
from . import morph

MIN_FREE_DISK_BYTES = 128 * 1024 * 1024  # reserva para logs, journal e sistema
RENDER_WORKERS_MAX = 3
STRIP = 512  # reduz o pico de memoria em folhas largas
MAX_STRIP_MEMORY_BYTES = 512 * 1024 * 1024
_BYTES_PER_RENDER_PIXEL = 96  # planos, alpha, CMYK float e buffers temporários
MAX_SOURCE_TRANSFORMS = 8
MAX_SOURCE_PROFILE_BYTES = 2 * 1024 * 1024
DEFAULT_SOURCE_DPI = 300.0
def _safe_source_dpi(value, default=DEFAULT_SOURCE_DPI):
    """Retorna um DPI finito e positivo; metadado ausente ou corrompido usa o padrão."""
    try:
        dpi = float(value)
    except (TypeError, ValueError):
        return default
    return dpi if math.isfinite(dpi) and dpi > 0 else default


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
        self._source_transforms = threading.local()
        if s.icc_path:
            try:
                if not os.path.isfile(s.icc_path):
                    raise FileNotFoundError(s.icc_path)
                srgb = ImageCms.createProfile("sRGB")
                prof = ImageCms.getOpenProfile(s.icc_path)
                flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if s.black_point_comp else 0
                # LittleCMS: transforme compartilhada por threads exige desativar cache de pixel.
                flags |= ImageCms.Flags.NOCACHE
                self.transform = ImageCms.buildTransform(
                    srgb, prof, "RGB", "CMYK", renderingIntent=ImageCms.Intent(s.intent), flags=flags)
            except Exception as exc:
                self.icc_error = f"Perfil ICC indisponivel ou invalido: {exc}"

    @staticmethod
    def _build_source_transform(embedded, mode, intent, flags):
        profile = ImageCms.ImageCmsProfile(io.BytesIO(embedded))
        return ImageCms.buildTransform(profile, ImageCms.createProfile("sRGB"), mode,
                                       "RGBA", renderingIntent=intent, flags=flags)

    def _source_transform(self, embedded, mode):
        flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if self.s.black_point_comp else 0
        intent = self.s.intent
        if MAX_SOURCE_TRANSFORMS <= 0 or len(embedded) > MAX_SOURCE_PROFILE_BYTES:
            return self._build_source_transform(embedded, mode, intent, flags)
        # Cada thread possui suas transformações: mantém o cache de pixels do
        # LittleCMS sem compartilhar estado mutável entre trabalhos simultâneos.
        local = self._source_transforms
        if not hasattr(local, "cache"):
            local.cache = OrderedDict()
            local.profile_bytes = 0
        key = (bytes(embedded), mode, intent, flags)
        cached = local.cache.get(key)
        if cached is not None:
            local.cache.move_to_end(key)
            return cached
        transform = self._build_source_transform(key[0], mode, intent, flags)
        local.cache[key] = transform
        local.profile_bytes += len(key[0])
        while (len(local.cache) > MAX_SOURCE_TRANSFORMS
               or local.profile_bytes > MAX_SOURCE_PROFILE_BYTES):
            previous, _ = local.cache.popitem(last=False)
            local.profile_bytes -= len(previous[0])
        return transform

    def _source_rgba(self, source: Image.Image, *, in_place=False) -> Image.Image:
        # Somente o carregador pode ceder um raster RGBA que acabou de decodificar.
        # Imagens mapeadas/read-only continuam no caminho com buffer independente.
        reuse = in_place and source.mode == "RGBA" and not source.readonly
        embedded = source.info.get("icc_profile")
        if not embedded:
            return source if reuse else source.convert("RGBA")
        try:
            mode = "RGB" if source.mode in ("P", "PA") else "L" if source.mode == "LA" else source.mode
            transform = self._source_transform(embedded, mode)
            if source.mode == "RGBA":
                if reuse:
                    ImageCms.applyTransform(source, transform, inPlace=True)
                    return source
                # LittleCMS/Pillow preservam o alfa em RGBA -> RGBA. Não crie
                # dois rasters RGB e outro canal A para restaurá-lo depois.
                return ImageCms.applyTransform(source, transform)
            if source.mode in ("RGBA", "P", "PA"):
                color = source.convert("RGB")
            elif source.mode == "LA":
                color = source.getchannel("L")
            else:
                color = source
            try:
                rgba = ImageCms.applyTransform(color, transform)
            finally:
                if color is not source:
                    color.close()
            try:
                if source.mode in ("RGBA", "LA", "PA"):
                    # O alfa já existe: não copie o raster RGBA inteiro para lê-lo.
                    alpha = source.getchannel("A")
                    try:
                        rgba.putalpha(alpha)
                    finally:
                        alpha.close()
                elif "transparency" in source.info:
                    # Paleta/chave de cor ainda precisam da expansão do Pillow.
                    expanded = source.convert("RGBA")
                    try:
                        alpha = expanded.getchannel("A")
                        try:
                            rgba.putalpha(alpha)
                        finally:
                            alpha.close()
                    finally:
                        expanded.close()
                else:
                    # RGB/LAB podem ter padding no quarto byte; CMYK não tem
                    # alfa. Nunca interprete esses bytes como transparência.
                    rgba.putalpha(255)
            except Exception:
                rgba.close()
                raise
            return rgba
        except Exception as exc:
            raise ValueError(f"Perfil ICC de entrada indisponivel ou invalido: {exc}") from exc

    def _load_source(self, path, source_ready=None):
        """Entrega um RGBA privado, com arquivo fechado e demais rasters liberados."""
        im = None
        with Image.open(path) as opened:
            try:
                if opened.width <= 0 or opened.height <= 0:
                    raise ValueError("A imagem precisa ter largura e altura maiores que zero.")
                orientation = opened.getexif().get(274, 1)
                # Sem rotação/reflexão, use a imagem aberta até a conversão RGBA.
                source = ImageOps.exif_transpose(opened) if orientation in (2, 3, 4, 5, 6, 7, 8) else opened
                try:
                    if source is not opened:
                        # A rotação possui um raster próprio; não retenha mais
                        # uma imagem inteira durante a transformação de cor.
                        opened.close()
                    source.load()
                    if source_ready is not None:
                        # A origem já está orientada, antes do ICC. O observador
                        # pode lê-la durante a chamada, sem reter ou alterar o raster.
                        source_ready(source)
                    has_alpha = source.mode in ("RGBA", "LA", "PA") or "transparency" in source.info
                    source_dpi = source.info.get("dpi", (DEFAULT_SOURCE_DPI, DEFAULT_SOURCE_DPI))
                    try:
                        raw_dpi_x, raw_dpi_y = source_dpi[0], source_dpi[1]
                    except (IndexError, TypeError):
                        raw_dpi_x = raw_dpi_y = DEFAULT_SOURCE_DPI
                    source_dpi_x, source_dpi_y = _safe_source_dpi(raw_dpi_x), _safe_source_dpi(raw_dpi_y)
                    if orientation in (5, 6, 7, 8):
                        source_dpi_x, source_dpi_y = source_dpi_y, source_dpi_x
                    im = self._source_rgba(source, in_place=True)
                finally:
                    if source is not opened and source is not im:
                        source.close()
            finally:
                # O context manager fecha o arquivo. Preserve apenas o raster
                # privado cuja propriedade foi transferida ao chamador.
                if opened is not im:
                    opened.close()
        return im, has_alpha, source_dpi_x, source_dpi_y

    @staticmethod
    def _prepare_resampling(im, n_dots, art_rows):
        # Pillow repete esta conversão da imagem inteira em cada resize RGBA.
        # Mantenha o atalho 1:1: converter e voltar pode quantizar cores com alfa.
        if (n_dots, art_rows) == im.size:
            return im
        prepared = im.convert("RGBa")
        im.close()
        return prepared

    # ---------- cor ----------
    def _to_cmyk(self, rgb: Image.Image) -> np.ndarray:
        if self.transform is not None:
            c = ImageCms.applyTransform(rgb, self.transform)
        else:
            c = rgb.convert("CMYK")
        a = np.asarray(c, dtype=np.float32) / 255.0          # (h,w,4) 1 = tinta cheia
        lim = [self.s.ink_limit.get(k, 100) / 100.0 for k in "CMYK"]
        a *= np.asarray(lim, dtype=np.float32)
        return np.clip(a, 0, 1, out=a)

    def _thresholds(self, height, width, y0):
        ny, nx = self.noise.shape
        return self.noise[np.ix_((np.arange(height) + y0) % ny, np.arange(width) % nx)]

    def _halftone(self, v: np.ndarray, y0: int, thresholds=None) -> np.ndarray:
        """v = volume de tinta (0..1, 1 = tudo gota grande) -> niveis {0,1,3}.
        Modelo medido nos .PRT reais (nivel 2 nunca usado): a gota pequena tem r~0,40 do volume da grande.
        v<=r : so gotas pequenas, cobertura v/r.  v>r : cobertura 100%, grandes na fracao (v-r)/(1-r).
        Conferido: branco 50% -> 16,7% de gotas grandes (real: 16,5%); 100% -> tudo nivel 3."""
        r = self.s.small_drop_ratio
        t = self._thresholds(*v.shape, y0) if thresholds is None else thresholds
        small = (v / r) > t
        large = ((v - r) / (1.0 - r)) > t
        # Escala uint8 evita dois buffers int64 da seleção aninhada.
        return np.where(large, np.uint8(3), small.astype(np.uint8))

    # ---------- branco ----------
    def _white_levels(self, alpha: np.ndarray, y0: int = 0, thresholds=None) -> np.ndarray:
        s = self.s
        a = alpha
        if s.white_density == 0 or not a.any():
            return np.zeros(a.shape, dtype=np.uint8)
        # fecha furos de meio-tom / areas claras: cobertura = alpha >= limiar
        original_mask = a >= s.white_alpha_threshold
        mask = morph.close_holes(original_mask, s.white_fill_holes_mm, s.dpi_x, s.dpi_y)
        mask = morph.erode(mask, s.white_choke_mm, s.dpi_x, s.dpi_y)
        # niveis: borda (alpha parcial) = 1, miolo = 3
        # densidade 100% = tudo gota grande (3); abaixo disso: gotas pequenas + grandes esparsas
        dens = np.where(a >= 0.9, s.white_density, 0.5 * (a / 0.9) * s.white_density).astype(np.float32)
        # Pixels transparentes adicionados pelo fechamento sao furos preenchidos:
        # sem esta atribuicao, a mascara fechava, mas a densidade continuava zero.
        dens[mask & ~original_mask] = s.white_density
        dens = np.where(mask, dens, 0.0)
        return self._halftone(dens, y0, thresholds)

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
    def process(self, png_path: str, out_path: str, width_cm: float = None, progress=None, before_publish=None, control=None, source_ready=None):
        s = self.s
        if self.icc_error:
            raise RuntimeError(self.icc_error)
        out_path = os.path.realpath(out_path)
        out_dir = os.path.dirname(out_path)
        os.makedirs(out_dir, exist_ok=True)
        im, has_alpha, source_dpi_x, source_dpi_y = (self._load_source(png_path) if source_ready is None
                                                  else self._load_source(png_path, source_ready=source_ready))
        try:
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
            fill_rows = int(np.ceil(s.white_fill_holes_mm / 25.4 * s.dpi_y)) if s.white_enabled else 0
            choke_rows = int(np.ceil(s.white_choke_mm / 25.4 * s.dpi_y)) if s.white_enabled else 0
            halo = 2 * fill_rows + choke_rows + 2
            workers = (min(RENDER_WORKERS_MAX, os.cpu_count() or 1)
                       if n_rows >= STRIP * 3 and n_dots * n_rows >= 1_000_000 else 1)
            available_rows = MAX_STRIP_MEMORY_BYTES // workers // max(1, n_dots * _BYTES_PER_RENDER_PIXEL) - 2 * halo
            if workers > 1 and available_rows < 1:
                workers = 1
                available_rows = MAX_STRIP_MEMORY_BYTES // max(1, n_dots * _BYTES_PER_RENDER_PIXEL) - 2 * halo
            if available_rows < 1:
                raise ValueError("A largura/DPI exigem mais memória do que o limite seguro de processamento por tira.")
            strip_rows = max(1, min(STRIP, int(available_rows)))
            im = self._prepare_resampling(im, n_dots, art_rows)
            fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(out_path)}.", suffix=".part", dir=out_dir)
            os.close(fd)
            wr = None
            try:
                wr = PrtWriter(tmp_path, s.dpi_x, s.dpi_y, n_rows, n_dots)
                if workers == 1:
                    y = 0
                    while y < n_rows:
                        if control:
                            control()
                        y1 = min(n_rows, y + strip_rows)
                        a0, a1 = max(0, y - halo), min(n_rows, y1 + halo)       # com halo para morfologia
                        planes_full = self._render(im, a0, a1, top, art_rows, n_dots, labels)
                        o = y - a0
                        blk = [p[o:o + (y1 - y)] for p in planes_full]
                        wr.write_block(blk)
                        # Libere a tira anterior antes de alocar a próxima e seus buffers EDT.
                        del blk, planes_full
                        y = y1
                        if progress:
                            progress(y / n_rows)
                        if control:
                            control()
                else:
                    from collections import deque
                    from concurrent.futures import ThreadPoolExecutor
                    ranges = iter(range(0, n_rows, strip_rows))
                    pending = deque()
                    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="autorip-render") as pool:
                        def submit():
                            if control:
                                control()
                            start = next(ranges, None)
                            if start is None:
                                return
                            end = min(n_rows, start + strip_rows)
                            a0, a1 = max(0, start - halo), min(n_rows, end + halo)
                            future = pool.submit(self._render, im, a0, a1, top, art_rows, n_dots, labels)
                            pending.append((start, end, a0, future))
                        for _ in range(workers):
                            submit()
                        while pending:
                            if control:
                                control()
                            start, end, a0, future = pending.popleft()
                            planes_full = future.result()
                            offset = start - a0
                            block = [plane[offset:offset + end - start] for plane in planes_full]
                            wr.write_block(block)
                            del block, planes_full, future
                            if progress:
                                progress(end / n_rows)
                            if control:
                                control()
                            submit()
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
        finally:
            im.close()

    def _render(self, im, a0, a1, top, art_rows, n_dots, labels):
        s = self.s
        h = a1 - a0
        zero = np.zeros((h, n_dots), np.uint8)
        planes = [zero] * 12
        r0, r1 = max(a0, top), min(a1, top + art_rows)
        if r1 > r0:
            sy = im.height / art_rows
            box = (0, (r0 - top) * sy, im.width, (r1 - top) * sy)
            strip = im.resize((n_dots, r1 - r0), Image.LANCZOS, box=box)
            if strip.mode == "RGBa":
                strip = strip.convert("RGBA")
            if s.mirror:
                strip = strip.transpose(Image.FLIP_LEFT_RIGHT)
            arr = np.asarray(strip)
            if arr[..., 3].any():
                alpha = arr[..., 3].astype(np.float32) / 255.0
                rgb = Image.fromarray(arr[..., :3], "RGB")
                cmyk = self._to_cmyk(rgb)
                cmyk *= alpha[..., None]  # tinta somente onde há arte, sem duplicar CMYK
                o = r0 - a0
                thresholds = self._thresholds(h, n_dots, a0)
                color_thresholds = thresholds[o:o + (r1 - r0)]
                idx = {"C": 0, "M": 1, "Y": 2, "K": 3}            # ordem do array CMYK do Pillow
                for pl, name in enumerate(s.channel_order):          # plano -> tinta
                    levels = self._halftone(cmyk[..., idx[name]], r0, color_thresholds)
                    if o == 0 and levels.shape[0] == h:
                        planes[pl] = levels
                    else:
                        planes[pl] = zero.copy()
                        planes[pl][o:o + levels.shape[0]] = levels
                # EDT usa buffers grandes: libere a cor e sua tela antes da morfologia.
                del color_thresholds, thresholds, cmyk, rgb, arr, strip
                if s.white_enabled:
                    full_alpha = np.zeros((h, n_dots), np.float32)
                    full_alpha[o:o + (r1 - r0)] = alpha
                    del alpha
                    lvl = self._white_levels(full_alpha, a0)
                    for pidx in s.white_planes:
                        planes[pidx] = lvl
        for (ly, lx, lab) in labels:                 # etiqueta em K (plano 0)
            ys, ye = max(ly, a0), min(ly + lab.shape[0], a1)
            if ye > ys:
                seg = lab[ys - ly:ye - ly]
                k_plane = s.channel_order.index("K")
                if planes[k_plane] is zero:
                    planes[k_plane] = zero.copy()
                dst = planes[k_plane][ys - a0:ye - a0, lx:lx + lab.shape[1]]
                dst[seg] = 3
        return planes
