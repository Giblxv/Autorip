#!/usr/bin/env bash
set -Eeuo pipefail

# Manutenção noturna do servidor AutoRIP.
# Limpa somente temporários antigos; nunca toca nas pastas /srv/autorip.
LOG_TAG="autorip-maintenance"
AGE_MINUTES="${AUTORIP_TEMP_AGE_MINUTES:-1440}"

log() { logger -t "${LOG_TAG}" -- "$*" || true; printf '[%s] %s\n' "${LOG_TAG}" "$*"; }

if [[ "${EUID}" -ne 0 ]]; then
  echo "Este script precisa ser executado como root." >&2
  exit 1
fi
if [[ ! "${AGE_MINUTES}" =~ ^[0-9]+$ ]]; then
  echo "AUTORIP_TEMP_AGE_MINUTES deve ser um número inteiro." >&2
  exit 1
fi

log "iniciando manutenção; temporários com mais de ${AGE_MINUTES} minutos serão removidos"
if ! systemctl stop autorip.service; then
  log "não foi possível parar o serviço AutoRIP; manutenção cancelada"
  exit 1
fi
if systemctl is-active --quiet autorip.service; then
  log "o serviço AutoRIP continua ativo; manutenção cancelada"
  exit 1
fi

# Respeita as regras do sistema (incluindo /tmp e /var/tmp) e evita remover
# arquivos recém-criados que ainda possam estar sendo usados por processos.
systemd-tmpfiles --clean

# Remove somente arquivos antigos nos diretórios temporários padrão. O -xdev
# impede atravessar para outros sistemas de arquivos montados.
for directory in /tmp /var/tmp; do
  if [[ -d "${directory}" ]]; then
    find "${directory}" -xdev -mindepth 1 -type f -mmin "+${AGE_MINUTES}" -delete
    find "${directory}" -xdev -mindepth 1 -type l -mmin "+${AGE_MINUTES}" -delete
    find "${directory}" -xdev -mindepth 1 -type d -empty -mmin "+${AGE_MINUTES}" -delete 2>/dev/null || true
  fi
done

sync
if [[ "${AUTORIP_MAINTENANCE_NO_REBOOT:-0}" == "1" ]]; then
  log "reinicialização suprimida por AUTORIP_MAINTENANCE_NO_REBOOT=1 (modo de teste)"
  systemctl start autorip.service 2>/dev/null || true
  exit 0
fi

log "manutenção concluída; reinicializando o servidor"
systemctl reboot
