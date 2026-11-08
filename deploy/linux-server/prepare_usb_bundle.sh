#!/usr/bin/env bash
set -Eeuo pipefail

# Cria um pacote portátil para levar ao Ubuntu Desktop instalado no SSD.
# O AutoRIP não é embutido em uma ISO ARM/x86 incompatível; a instalação ocorre
# no primeiro boot do Ubuntu Desktop x86_64.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-${ROOT}/dist/autorip-linux-server}"
mkdir -p "${OUT}/deploy/linux-server" "${OUT}/docs"
cp -a "${ROOT}/deploy/linux-server/autorip.service" \
      "${ROOT}/deploy/linux-server/install_autorip_server.sh" \
      "${OUT}/deploy/linux-server/"
cp -a "${ROOT}/README.md" "${ROOT}/docs/LINUX_SERVIDOR_DESKTOP.md" "${OUT}/docs/"
cp -a "${ROOT}/autorip" "${ROOT}/autorip_gui.py" "${ROOT}/requirements.txt" "${OUT}/"
chmod 0755 "${OUT}/deploy/linux-server/install_autorip_server.sh"
cat > "${OUT}/INSTALAR.txt" <<'EOF'
1. Instale Ubuntu Desktop LTS x86_64 no SSD de destino.
2. Conecte o PC à rede por Ethernet.
3. Copie esta pasta para o PC e execute:

   sudo ./deploy/linux-server/install_autorip_server.sh

4. Defina a senha do compartilhamento Samba quando solicitado.
5. Configure o perfil ICC em /var/lib/autorip/autorip.json.
6. Configure o IP fixo conforme docs/LINUX_SERVIDOR_DESKTOP.md.
EOF
printf 'Pacote criado em %s\n' "${OUT}"
