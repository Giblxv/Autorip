#!/usr/bin/env bash
set -Eeuo pipefail

# Instala o AutoRIP como serviço local em Ubuntu Desktop/Server.
# Execute a partir da raiz do projeto: sudo ./deploy/linux-server/install_autorip_server.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_ROOT="${AUTORIP_INSTALL_ROOT:-/opt/autorip}"
DATA_ROOT="${AUTORIP_DATA_ROOT:-/srv/autorip}"
STATE_ROOT="${AUTORIP_STATE_ROOT:-/var/lib/autorip}"
ETC_ROOT="${AUTORIP_ETC_ROOT:-/etc/autorip}"
SERVICE_USER="${AUTORIP_USER:-autorip}"
SHARE_USER="${AUTORIP_SHARE_USER:-autorip}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Execute como root: sudo $0" >&2
  exit 1
fi

if [[ ! -f "${PROJECT_ROOT}/requirements.txt" || ! -d "${PROJECT_ROOT}/autorip" ]]; then
  echo "Execute este script a partir de uma cópia completa do projeto AutoRIP." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-dev python3-pip \
  build-essential libjpeg-dev zlib1g-dev libtiff-dev libopenjp2-7 \
  samba smbclient ufw

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${STATE_ROOT}" --create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

# Um login Samba compartilhado, conforme a implantação solicitada.
if ! id -u "${SHARE_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${STATE_ROOT}" --shell /usr/sbin/nologin "${SHARE_USER}"
fi

mkdir -p "${INSTALL_ROOT}" "${DATA_ROOT}"/{hot,saida,impressos,feito,erro,recovery} \
  "${STATE_ROOT}" "${ETC_ROOT}"

# O estado fica privado; os diretórios operacionais pertencem ao grupo compartilhado.
install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${STATE_ROOT}"
install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${ETC_ROOT}"
cp -a "${PROJECT_ROOT}/autorip" "${PROJECT_ROOT}/autorip_gui.py" "${PROJECT_ROOT}/requirements.txt" "${INSTALL_ROOT}/"
if [[ -f "${PROJECT_ROOT}/requirements-dev.txt" ]]; then
  cp -a "${PROJECT_ROOT}/requirements-dev.txt" "${INSTALL_ROOT}/"
fi
chown -R root:root "${INSTALL_ROOT}"

# Acesso remoto opcional, ativado por padrão para a imagem do servidor.
if [[ "${AUTORIP_INSTALL_REMOTE_ACCESS:-1}" == "1" ]]; then
  install -m 0755 "${PROJECT_ROOT}/deploy/linux-server/install_remote_access.sh" /tmp/autorip-install-remote-access.sh
  AUTORIP_LAN_CIDR="${AUTORIP_LAN_CIDR:-192.168.0.0/16}" \
    AUTORIP_DESKTOP_USER="${AUTORIP_DESKTOP_USER:-}" \
    /tmp/autorip-install-remote-access.sh
  rm -f /tmp/autorip-install-remote-access.sh
fi

python3 -m venv --clear "${INSTALL_ROOT}/venv"
"${INSTALL_ROOT}/venv/bin/python" -m pip install --upgrade pip
"${INSTALL_ROOT}/venv/bin/python" -m pip install -r "${INSTALL_ROOT}/requirements.txt"

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_ROOT}"
chmod 2770 "${DATA_ROOT}"/{hot,saida,impressos,feito,erro,recovery}

cat > "${ETC_ROOT}/autorip.env" <<EOF
AUTORIP_HOME=${STATE_ROOT}
EOF
chmod 0640 "${ETC_ROOT}/autorip.env"
chown root:"${SERVICE_USER}" "${ETC_ROOT}/autorip.env"

if [[ ! -f "${STATE_ROOT}/autorip.json" ]]; then
  cat > "${STATE_ROOT}/autorip.json" <<EOF
{
  "icc_path": "",
  "offline_mode": true,
  "auto_mode": true,
  "auto_update": false,
  "poll_seconds": 2.0,
  "hot_folder": "${DATA_ROOT}/hot",
  "output_folder": "${DATA_ROOT}/saida",
  "printed_folder": "${DATA_ROOT}/impressos",
  "done_folder": "${DATA_ROOT}/feito",
  "error_folder": "${DATA_ROOT}/erro"
}
EOF
  chown "${SERVICE_USER}:${SERVICE_USER}" "${STATE_ROOT}/autorip.json"
  chmod 0600 "${STATE_ROOT}/autorip.json"
fi

install -m 0644 "${PROJECT_ROOT}/deploy/linux-server/autorip.service" /etc/systemd/system/autorip.service

# Samba usa o mesmo usuário lógico do serviço. A senha é solicitada sem aparecer na tela.
if [[ "${SERVICE_USER}" != "${SHARE_USER}" ]]; then
  usermod -a -G "${SERVICE_USER}" "${SHARE_USER}"
fi
if [[ -n "${AUTORIP_SMB_PASSWORD:-}" ]]; then
  printf '%s\n%s\n' "${AUTORIP_SMB_PASSWORD}" "${AUTORIP_SMB_PASSWORD}" | smbpasswd -a -s "${SHARE_USER}"
else
  printf 'Defina a senha do compartilhamento SMB para o login comum (%s):\n' "${SHARE_USER}"
  smbpasswd -a "${SHARE_USER}"
fi
smbpasswd -e "${SHARE_USER}"

# Inclui somente a configuração gerenciada pelo AutoRIP, preservando o smb.conf existente.
if ! grep -q '^# BEGIN AUTORIP MANAGED SHARES$' /etc/samba/smb.conf; then
  cat >> /etc/samba/smb.conf <<EOF

# BEGIN AUTORIP MANAGED SHARES
[AutoRIP-Entrada]
   path = ${DATA_ROOT}/hot
   browseable = yes
   read only = no
   valid users = ${SHARE_USER}
   force group = ${SERVICE_USER}
   create mask = 0660
   force create mode = 0660
   directory mask = 2770
   force directory mode = 2770

[AutoRIP-Saida]
   path = ${DATA_ROOT}/saida
   browseable = yes
   read only = yes
   valid users = ${SHARE_USER}

[AutoRIP-Feito]
   path = ${DATA_ROOT}/feito
   browseable = yes
   read only = yes
   valid users = ${SHARE_USER}

[AutoRIP-Erros]
   path = ${DATA_ROOT}/erro
   browseable = yes
   read only = yes
   valid users = ${SHARE_USER}
# END AUTORIP MANAGED SHARES
EOF
fi

testparm -s >/dev/null
systemctl daemon-reload
systemctl enable --now autorip.service
systemctl enable --now smbd

# Firewall: SMB apenas na rede local; ajuste a sub-rede se necessário.
ufw allow from 192.168.0.0/16 to any app Samba comment 'AutoRIP SMB rede local' || true
ufw allow from 10.0.0.0/8 to any app Samba comment 'AutoRIP SMB rede local' || true
ufw allow from 172.16.0.0/12 to any app Samba comment 'AutoRIP SMB rede local' || true

cat <<EOF

AutoRIP instalado.

Serviço:       systemctl status autorip
Configuração:  ${STATE_ROOT}/autorip.json
Entrada:       ${DATA_ROOT}/hot
Saída PRT:     ${DATA_ROOT}/saida
Interface:      Ubuntu Desktop para administração; o worker é um único serviço systemd

Edite o ICC antes de operar:
  sudoedit ${STATE_ROOT}/autorip.json
  sudo systemctl restart autorip

Para validar:
  journalctl -u autorip -f
  smbclient -L localhost -U ${SHARE_USER}
EOF
