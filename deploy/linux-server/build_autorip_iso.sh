#!/usr/bin/env bash
set -Eeuo pipefail

# Gera uma ISO híbrida UEFI/BIOS baseada na ISO oficial Ubuntu Desktop amd64.
# Uso: ./build_autorip_iso.sh ubuntu-24.04-desktop-amd64.iso autorip-server.iso
# A ISO apaga o maior disco encontrado pelo instalador. Use somente no PC dedicado.

BASE_ISO="${1:-}"
OUTPUT_ISO="${2:-autorip-server.iso}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -z "${BASE_ISO}" || ! -f "${BASE_ISO}" ]]; then
  echo "Informe uma ISO oficial Ubuntu Desktop amd64 existente." >&2
  echo "Uso: $0 ubuntu-24.04-desktop-amd64.iso autorip-server.iso" >&2
  exit 2
fi
for command in xorriso openssl base64; do
  command -v "${command}" >/dev/null || { echo "Ferramenta ausente: ${command}" >&2; exit 1; }
done
command -v python3 >/dev/null || { echo "Ferramenta ausente: python3" >&2; exit 1; }

read -r -p 'Hostname [autorip-server]: ' HOSTNAME
HOSTNAME="${HOSTNAME:-autorip-server}"
read -r -p 'Usuário administrador [autoripadmin]: ' ADMIN_USER
ADMIN_USER="${ADMIN_USER:-autoripadmin}"
read -r -s -p 'Senha do administrador: ' ADMIN_PASSWORD; echo
read -r -s -p 'Senha do compartilhamento Samba: ' SMB_PASSWORD; echo
read -r -p 'CIDR da rede local [192.168.1.0/24]: ' LAN_CIDR
LAN_CIDR="${LAN_CIDR:-192.168.1.0/24}"

[[ "${HOSTNAME}" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,62}$ ]] || { echo 'Hostname inválido.' >&2; exit 1; }
[[ "${ADMIN_USER}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || { echo 'Usuário administrador inválido.' >&2; exit 1; }
LAN_CIDR="${LAN_CIDR}" python3 - <<'PY'
import ipaddress
import os
try:
    ipaddress.ip_network(os.environ["LAN_CIDR"], strict=False)
except ValueError as exc:
    raise SystemExit(f"CIDR inválido: {exc}")
PY

if [[ ${#ADMIN_PASSWORD} -lt 8 || ${#SMB_PASSWORD} -lt 8 ]]; then
  echo 'As senhas precisam ter pelo menos 8 caracteres.' >&2
  exit 1
fi

ADMIN_HASH="$(openssl passwd -6 -- "${ADMIN_PASSWORD}")"
SMB_B64="$(printf '%s' "${SMB_PASSWORD}" | base64 -w0)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/iso" "${TMP}/bundle"
xorriso -osirrox on -indev "${BASE_ISO}" -extract / "${TMP}/iso" >/dev/null
"${ROOT}/deploy/linux-server/prepare_usb_bundle.sh" "${TMP}/bundle"
cp -a "${TMP}/bundle" "${TMP}/iso/autorip-server-bundle"

cat > "${TMP}/iso/autoinstall.yaml" <<EOF
#cloud-config
autoinstall:
  version: 1
  locale: pt_BR.UTF-8
  keyboard:
    layout: br
  timezone: America/Sao_Paulo
  source:
    search_drivers: true
  storage:
    layout:
      name: lvm
  identity:
    hostname: ${HOSTNAME}
    username: ${ADMIN_USER}
    password: '${ADMIN_HASH}'
  ssh:
    install-server: true
    allow-pw: false
  packages:
    - ubuntu-desktop
    - firefox
    - git
  late-commands:
    - mkdir -p /target/opt/autorip-server
    - cp -a /cdrom/autorip-server-bundle/. /target/opt/autorip-server/
    - curtin in-target --target=/target -- bash -c 'echo ${SMB_B64} | base64 -d > /tmp/autorip-smb-password'
    - curtin in-target --target=/target -- bash -c 'chmod 600 /tmp/autorip-smb-password; AUTORIP_SMB_PASSWORD="$(cat /tmp/autorip-smb-password)" AUTORIP_LAN_CIDR="${LAN_CIDR}" AUTORIP_DESKTOP_USER="${ADMIN_USER}" /opt/autorip-server/deploy/linux-server/install_autorip_server.sh; rm -f /tmp/autorip-smb-password'
EOF

# Ativa o modo autoinstall nas entradas BIOS/UEFI da mídia.
for config in "${TMP}/iso/boot/grub/grub.cfg" "${TMP}/iso/isolinux/txt.cfg"; do
  if [[ -f "${config}" ]]; then
    sed -i 's#---#autoinstall ds=nocloud;s=/cdrom/ ---#g' "${config}"
  fi
done

# Mantém o boot híbrido da mídia Ubuntu original.
xorriso -as mkisofs \
  -r -V 'AUTORIP-UBUNTU' -J -joliet-long -l -iso-level 3 \
  -o "${OUTPUT_ISO}" \
  -isohybrid-mbr "${TMP}/iso/isolinux/isohdpfx.bin" \
  -partition_offset 16 -c isolinux/boot.cat \
  -b isolinux/isolinux.bin -no-emul-boot -boot-load-size 4 -boot-info-table \
  -eltorito-alt-boot -e boot/grub/efi.img -no-emul-boot \
  -isohybrid-gpt-basdat "${TMP}/iso" >/dev/null

chmod 0644 "${OUTPUT_ISO}"
sha256sum "${OUTPUT_ISO}" > "${OUTPUT_ISO}.sha256"
cat <<EOF

ISO criada: ${OUTPUT_ISO}
Checksum:   ${OUTPUT_ISO}.sha256

ATENÇÃO: esta ISO instala automaticamente e apaga o maior disco selecionado pelo Ubuntu.
As senhas foram embutidas na ISO durante a criação; trate o arquivo como confidencial.
EOF
