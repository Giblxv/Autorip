#!/usr/bin/env bash
set -Eeuo pipefail

# Instala acesso remoto apenas na rede privada local.
# Variáveis opcionais: AUTORIP_DESKTOP_USER e AUTORIP_LAN_CIDR.

if [[ "${EUID}" -ne 0 ]]; then
  echo "Execute como root: sudo $0" >&2
  exit 1
fi

LAN_CIDR="${AUTORIP_LAN_CIDR:-192.168.0.0/16}"
DESKTOP_USER="${AUTORIP_DESKTOP_USER:-}"
LAN_CIDR="${LAN_CIDR}" python3 - <<'PY'
import ipaddress
import os

try:
    ipaddress.ip_network(os.environ["LAN_CIDR"], strict=False)
except ValueError as exc:
    raise SystemExit(f"CIDR inválido: {exc}")
PY
if [[ -z "${DESKTOP_USER}" ]]; then
  DESKTOP_USER="$(awk -F: '$3 >= 1000 && $3 < 60000 && $7 !~ /(nologin|false)$/ {print $1; exit}' /etc/passwd || true)"
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends xrdp xorgxrdp cockpit

if [[ -n "${DESKTOP_USER}" ]] && id -u "${DESKTOP_USER}" >/dev/null 2>&1; then
  adduser "${DESKTOP_USER}" ssl-cert || true
  echo "Usuário XRDP: ${DESKTOP_USER}"
else
  echo "AVISO: nenhum usuário desktop encontrado; crie um usuário Ubuntu antes de usar XRDP." >&2
fi

systemctl enable --now xrdp
systemctl enable --now cockpit.socket

# Não habilita UFW automaticamente se ele já estiver ativo com política externa.
# As regras são específicas para a sub-rede interna informada.
ufw allow from "${LAN_CIDR}" to any port 3389 proto tcp comment 'AutoRIP XRDP rede interna' || true
ufw allow from "${LAN_CIDR}" to any port 9090 proto tcp comment 'AutoRIP Cockpit rede interna' || true
ufw allow from "${LAN_CIDR}" to any app Samba comment 'AutoRIP SMB rede interna' || true

cat <<EOF

Acesso remoto instalado.

XRDP:    mstsc.exe -> IP deste PC (porta 3389)
Cockpit: https://IP-DESTE-PC:9090
Rede:    ${LAN_CIDR}
Usuário: ${DESKTOP_USER:-crie um usuário desktop}

Não publique as portas 3389 ou 9090 no roteador. Para acesso externo, use VPN.
EOF
