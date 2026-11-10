"""Política de imagens compartilhada pelo RIP e pelas entradas do programa."""
from PIL import Image

# As artes não têm teto fixo de pixels, inclusive na leitura de cabeçalhos.
# Configure uma vez por processo, antes das aberturas concorrentes do painel;
# alternar este valor por requisição criaria corridas entre uploads e o RIP.
Image.MAX_IMAGE_PIXELS = None
