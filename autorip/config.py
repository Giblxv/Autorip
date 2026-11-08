"""Configuração validada do AutoRIP.

O arquivo pode conter tokens de integrações; ele é gravado atomicamente e com
permissões privadas quando o sistema operacional suporta chmod POSIX.
"""
import json
import ipaddress
import math
import os
import tempfile
from dataclasses import dataclass, asdict, field
from urllib.parse import urlsplit


@dataclass
class Settings:
    icc_path: str = ""                 # perfil ICC CMYK
    intent: int = 1                    # 0 perceptual, 1 relativo, 2 saturacao, 3 absoluto
    black_point_comp: bool = True
    channel_order: list = field(default_factory=lambda: ["K", "C", "M", "Y"])
    dpi_x: int = 720
    dpi_y: int = 2400
    mirror: bool = True
    margin_top_in: float = 0.5
    margin_bottom_in: float = 0.5
    ink_limit: dict = field(default_factory=lambda: {"C": 100, "M": 100, "Y": 100, "K": 100})
    # Branco automatico
    white_enabled: bool = True
    white_alpha_threshold: float = 0.02
    white_choke_mm: float = 0.10
    small_drop_ratio: float = 0.40
    white_density: float = 1.0
    white_fill_holes_mm: float = 0.30
    white_planes: list = field(default_factory=lambda: [4])
    offline_mode: bool = True
    # Marca e aparencia
    brand_name: str = "AutoRIP"
    brand_logo: str = ""
    watermark_path: str = ""
    watermark_opacity: float = 0.25
    label_enabled: bool = True
    # Integracoes
    webhook_url: str = ""
    trello_key: str = ""
    trello_token: str = ""
    trello_base: str = "https://api.trello.com/1"
    trello_in_list: str = ""
    trello_in_lists: list = field(default_factory=list)
    trello_out_list: str = ""
    trello_attachment_extensions: str = "png,tif,tiff,jpg,jpeg"
    trello_attachment_patterns: str = ""
    trello_scan_seconds: float = 30.0
    notion_token: str = ""
    notion_db: str = ""
    notion_base: str = "https://api.notion.com/v1"
    jira_url: str = ""
    jira_email: str = ""
    jira_token: str = ""
    jira_project: str = ""
    # Agente opcional: apenas sugere
    anthropic_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_base: str = "https://api.anthropic.com"
    # Pastas
    hot_folder: str = "hot_folder"
    output_folder: str = "saida"
    printed_folder: str = "impressos"
    done_folder: str = "feito"
    error_folder: str = "erro"
    auto_mode: bool = True
    auto_update: bool = True
    poll_seconds: float = 2.0

    def canonicalize_folders(self, base=None):
        """Converte pastas em caminhos físicos, resolvendo symlinks antes de segmentos `..`."""
        for name in ("hot_folder", "output_folder", "printed_folder", "done_folder", "error_folder"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Configuracao invalida: {name} nao pode ficar vazio.")
            if base is not None and not os.path.isabs(value):
                value = os.path.join(base, value)
            setattr(self, name, os.path.realpath(value))
        return self

    def validate(self):
        """Valida todos os valores que influenciam tinta, geometria e recursos."""
        def number(name, minimum, maximum, integer=False):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Configuracao invalida: {name} precisa ser numerico.")
            if integer and not isinstance(value, int):
                raise ValueError(f"Configuracao invalida: {name} precisa ser inteiro.")
            if value < minimum or value > maximum:
                raise ValueError(f"Configuracao invalida: {name} precisa estar entre {minimum} e {maximum}.")

        for name in ("black_point_comp", "mirror", "white_enabled", "offline_mode", "label_enabled", "auto_mode", "auto_update"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"Configuracao invalida: {name} precisa ser verdadeiro ou falso.")

        number("dpi_x", 72, 9600, integer=True)
        number("dpi_y", 72, 9600, integer=True)
        number("intent", 0, 3, integer=True)
        number("margin_top_in", 0, 10)
        number("margin_bottom_in", 0, 10)
        number("white_alpha_threshold", 0, 1)
        number("white_choke_mm", 0, 2)
        number("small_drop_ratio", 0.05, 0.95)
        number("white_density", 0, 1)
        number("white_fill_holes_mm", 0, 2)
        number("watermark_opacity", 0, 1)
        number("poll_seconds", 0.25, 120)
        number("trello_scan_seconds", 10, 3600)

        if (not isinstance(self.channel_order, list) or len(self.channel_order) != 4
                or any(type(channel) is not str for channel in self.channel_order)
                or set(self.channel_order) != {"K", "C", "M", "Y"}):
            raise ValueError("Configuracao invalida: channel_order precisa ser uma permutacao de K, C, M e Y.")
        if not isinstance(self.white_planes, list) or any(type(p) is not int or p < 4 or p > 11 for p in self.white_planes) or len(set(self.white_planes)) != len(self.white_planes):
            raise ValueError("Configuracao invalida: white_planes aceita canais unicos de 4 a 11.")
        if self.white_enabled and not self.white_planes:
            raise ValueError("Configuracao invalida: selecione pelo menos um canal de branco ou desative o branco automatico.")
        if not isinstance(self.ink_limit, dict) or set(self.ink_limit) != {"K", "C", "M", "Y"}:
            raise ValueError("Configuracao invalida: ink_limit precisa ter K, C, M e Y.")
        for channel, value in self.ink_limit.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 100:
                raise ValueError(f"Configuracao invalida: limite de tinta {channel} precisa estar entre 0 e 100%.")

        string_fields = (
            "icc_path", "brand_name", "brand_logo", "watermark_path", "webhook_url",
            "trello_key", "trello_token", "trello_base", "trello_in_list", "trello_out_list",
            "trello_attachment_extensions", "trello_attachment_patterns",
            "notion_token", "notion_db", "notion_base", "jira_url", "jira_email", "jira_token",
            "jira_project", "anthropic_key", "anthropic_model", "anthropic_base", "hot_folder",
            "output_folder", "printed_folder", "done_folder", "error_folder"
        )
        for name in string_fields:
            value = getattr(self, name)
            if not isinstance(value, str) or "\x00" in value:
                raise ValueError(f"Configuracao invalida: {name} precisa ser texto valido.")
        if (not isinstance(self.trello_in_lists, list) or len(self.trello_in_lists) > 32
                or any(not isinstance(item, str) or not item.strip() or "\x00" in item
                       for item in self.trello_in_lists)):
            raise ValueError("Configuracao invalida: trello_in_lists precisa ser uma lista de IDs de listas.")
        extensions = [item.strip().lower().lstrip(".")
                      for item in self.trello_attachment_extensions.replace(";", ",").split(",")
                      if item.strip()]
        if not extensions or any(not item.isalnum() or len(item) > 10 for item in extensions):
            raise ValueError("Configuracao invalida: extensoes de anexos Trello invalidas.")

        folders = ("hot_folder", "output_folder", "printed_folder", "done_folder", "error_folder")
        canonical = {}
        for name in folders:
            value = getattr(self, name)
            if not value.strip():
                raise ValueError(f"Configuracao invalida: {name} nao pode ficar vazio.")
            canonical[name] = os.path.normcase(os.path.realpath(value))
        for index, left in enumerate(folders):
            for right in folders[index + 1:]:
                a, b = canonical[left], canonical[right]
                try:
                    common = os.path.commonpath((a, b))
                except ValueError:  # unidades/volumes diferentes no Windows
                    continue
                if common == a or common == b:
                    raise ValueError(f"Configuracao invalida: as pastas {left} e {right} precisam ser distintas e nao sobrepostas.")

        def endpoint(name, value, hosts=None):
            if not value:
                return
            try:
                parsed = urlsplit(value)
                host = (parsed.hostname or "").lower().rstrip(".")
                _ = parsed.port
            except ValueError as exc:
                raise ValueError(f"Configuracao invalida: URL {name} malformada.") from exc
            if not host or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError(f"Configuracao invalida: URL {name} nao deve conter credenciais, query ou fragmento.")
            if hosts and not any(host == allowed or host.endswith("." + allowed) for allowed in hosts):
                if not (parsed.scheme == "http" and _is_loopback(host)):
                    raise ValueError(f"Configuracao invalida: host de {name} fora da allowlist.")
            if parsed.scheme == "https":
                return
            if parsed.scheme == "http" and _is_loopback(host):
                return
            raise ValueError(f"Configuracao invalida: {name} precisa usar HTTPS.")

        def _is_loopback(host):
            if host == "localhost":
                return True
            try:
                return ipaddress.ip_address(host).is_loopback
            except ValueError:
                return False

        endpoint("webhook_url", self.webhook_url)
        endpoint("trello_base", self.trello_base, ("trello.com",))
        endpoint("notion_base", self.notion_base, ("notion.com",))
        endpoint("jira_url", self.jira_url)
        endpoint("anthropic_base", self.anthropic_base, ("anthropic.com",))
        if len(self.brand_name) > 100:
            raise ValueError("Configuracao invalida: brand_name pode ter no maximo 100 caracteres.")
        return self

    @staticmethod
    def load(path, base=None):
        settings = Settings()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as source:
                data = json.load(source)
            if not isinstance(data, dict):
                raise ValueError("O arquivo de configuracao precisa conter um objeto JSON.")
            for key, value in data.items():
                if key in settings.__dataclass_fields__:
                    setattr(settings, key, value)
        if base is not None:
            settings.canonicalize_folders(base)
        return settings.validate()

    def save(self, path):
        self.validate()
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(asdict(self), target, indent=2, ensure_ascii=False)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.remove(temporary)
            except OSError:
                pass
            raise
