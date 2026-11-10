"""Remoção de fundo opcional com rembg/ONNX e modelo local explícito.

Não baixa modelos e não faz parte do executável padrão. O modelo escolhido
pelo operador precisa ser compatível com a sessão u2net_custom do rembg.
"""
import os
import tempfile

from PIL import ImageOps
from .imaging import Image
from .paths import publish_unique_file


def remove_background(src: str, dst: str, model_path: str = None, alpha_cut: int = 0):
    """Publica PNG RGBA sem sobrescrever arquivos; retorna o caminho utilizado."""
    if not model_path:
        raise ValueError("Informe model_path com um modelo ONNX local; downloads automaticos sao desativados.")
    if not os.path.isfile(model_path):
        raise FileNotFoundError(model_path)
    if type(alpha_cut) is not int or not 0 <= alpha_cut <= 255:
        raise ValueError("alpha_cut precisa ser inteiro entre 0 e 255.")
    try:
        from rembg import remove, new_session
    except ImportError as exc:
        raise RuntimeError("Instale o modulo opcional: pip install rembg onnxruntime") from exc
    session = new_session("u2net_custom", model_path=os.path.realpath(model_path))
    with Image.open(src) as image:
        out = remove(ImageOps.exif_transpose(image).convert("RGBA"), session=session).convert("RGBA")
    if alpha_cut:
        alpha = out.getchannel("A").point(lambda value: 0 if value < alpha_cut else value)
        out.putalpha(alpha)
    dst = os.path.abspath(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".bgremove.", suffix=".part", dir=os.path.dirname(dst))
    os.close(fd)
    try:
        out.save(temporary, "PNG")
        return publish_unique_file(temporary, dst)
    finally:
        try: os.remove(temporary)
        except FileNotFoundError: pass
