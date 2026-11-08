import json, os
from dataclasses import dataclass, asdict, field


@dataclass
class Settings:
    icc_path: str = ""                 # perfil ICC CMYK (ex.: Sublinks_DTF_E602 ... .icc)
    intent: int = 1                    # 0 perceptual, 1 relativo, 2 saturacao, 3 absoluto
    black_point_comp: bool = True
    channel_order: list = field(default_factory=lambda: ["K", "C", "M", "Y"])  # planos 0..3 (PROVAVEL, falta confirmar)
    dpi_x: int = 720
    dpi_y: int = 2400
    mirror: bool = True                # DTF imprime espelhado
    margin_top_in: float = 0.5         # polegadas de branco no inicio/fim do rolo
    margin_bottom_in: float = 0.5
    ink_limit: dict = field(default_factory=lambda: {"C": 100, "M": 100, "Y": 100, "K": 100})
    # --- branco automatico ---
    white_enabled: bool = True
    white_alpha_threshold: float = 0.02   # alpha minimo para receber branco
    white_choke_mm: float = 0.10          # recuo do branco nas bordas (evita halo)
    small_drop_ratio: float = 0.40        # volume da gota pequena / grande (medido)
    white_density: float = 1.0            # 0..1 (1 = branco cheio, nivel 3)
    white_fill_holes_mm: float = 0.30     # fecha furos do meio-tom sob a cor
    white_planes: list = field(default_factory=lambda: [4])   # nos testes TESTER1_0/_1 so o plano 4 tem branco
    offline_mode: bool = True          # sem internet: integracoes e agente ficam desligados (avisos vao para a fila)
    # --- marca / aparencia ---
    brand_name: str = "AutoRIP"
    brand_logo: str = ""               # PNG da marca (cabecalho e miniaturas)
    watermark_path: str = ""           # marca d'agua (cliente) aplicada nas miniaturas
    watermark_opacity: float = 0.25
    label_enabled: bool = True         # etiqueta "arquivo L x A cm" em K nas margens (como o FlexiPRINT)
    # --- integracoes de pedidos ---
    webhook_url: str = ""
    trello_key: str = ""
    trello_token: str = ""
    trello_base: str = "https://api.trello.com/1"
    trello_in_list: str = ""           # lista de ENTRADA: anexos de imagem viram arquivos na hot folder
    trello_out_list: str = ""          # lista onde o cartao "RIP pronto" e criado
    notion_token: str = ""
    notion_db: str = ""                # banco com propriedade de titulo chamada "Name"
    notion_base: str = "https://api.notion.com/v1"
    jira_url: str = ""                 # ex.: https://empresa.atlassian.net
    jira_email: str = ""
    jira_token: str = ""
    jira_project: str = ""
    # --- agente de IA (opcional: so sugere, nunca aplica sozinho) ---
    anthropic_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_base: str = "https://api.anthropic.com"
    # --- pastas (hot folder) ---
    hot_folder: str = "hot_folder"
    output_folder: str = "saida"
    printed_folder: str = "impressos"
    done_folder: str = "feito"
    error_folder: str = "erro"
    auto_mode: bool = True
    poll_seconds: float = 2.0

    @staticmethod
    def load(path):
        s = Settings()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    if hasattr(s, k):
                        setattr(s, k, v)
        return s

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
