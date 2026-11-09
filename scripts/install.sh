#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
MOBILE="$ROOT/mobile"
ANDROID_DIR="$MOBILE/android"
APK="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"

usage() {
  cat <<'EOF'
Uso: ./scripts/install.sh [opção]

  --server       cria/atualiza o ambiente Python do AutoRIP
  --mobile       instala dependências JS, sincroniza e compila o APK
  --install      instala o APK no primeiro telefone ADB autorizado
  --all          executa --server e --mobile
  --help         mostra esta ajuda

Exemplos:
  ./scripts/install.sh --all
  ./scripts/install.sh --mobile --install
EOF
}

SERVER=0
MOBILE_BUILD=0
INSTALL=0
if (($# == 0)); then usage; exit 2; fi
while (($#)); do
  case "$1" in
    --server) SERVER=1 ;;
    --mobile) MOBILE_BUILD=1 ;;
    --install) INSTALL=1; MOBILE_BUILD=1 ;;
    --all) SERVER=1; MOBILE_BUILD=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Opção desconhecida: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if ((SERVER)); then
  command -v python3 >/dev/null || { echo "Python 3 não encontrado." >&2; exit 1; }
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"
  "$VENV/bin/python" -m compileall -q "$ROOT/autorip" "$ROOT/autorip_gui.py"
  echo "Servidor preparado em $VENV"
fi

if ((MOBILE_BUILD)); then
  command -v node >/dev/null || { echo "Node.js não encontrado." >&2; exit 1; }
  command -v npm >/dev/null || { echo "npm não encontrado." >&2; exit 1; }
  [[ -x "$ANDROID_DIR/gradlew" ]] || { echo "Projeto Android não encontrado." >&2; exit 1; }
  (cd "$MOBILE" && npm ci && npx cap sync android)
  if [[ -z "${JAVA_HOME:-}" ]]; then
    for candidate in /usr/lib/jvm/java-17-openjdk-* /usr/lib/jvm/java-17-*; do
      if [[ -x "$candidate/bin/java" ]]; then export JAVA_HOME="$candidate"; break; fi
    done
  fi
  [[ -x "${JAVA_HOME:-}/bin/java" ]] || { echo "JDK 17 não encontrado. Defina JAVA_HOME." >&2; exit 1; }
  [[ -n "${ANDROID_HOME:-}" ]] || export ANDROID_HOME="${ANDROID_SDK_ROOT:-}"
  [[ -n "${ANDROID_HOME:-}" ]] || { echo "Android SDK não encontrado. Defina ANDROID_HOME." >&2; exit 1; }
  (cd "$ANDROID_DIR" && ./gradlew assembleDebug --no-daemon)
  [[ -s "$APK" ]] || { echo "APK não foi gerado." >&2; exit 1; }
  sha256sum "$APK"
  echo "APK gerado: $APK"
fi

if ((INSTALL)); then
  command -v adb >/dev/null || { echo "adb não encontrado. Instale Android platform-tools." >&2; exit 1; }
  [[ -s "$APK" ]] || { echo "Gere o APK antes da instalação." >&2; exit 1; }
  mapfile -t DEVICES < <(adb devices | awk 'NR>1 && $2 == "device" {print $1}')
  if ((${#DEVICES[@]} == 0)); then
    echo "Nenhum telefone ADB autorizado. Ative Depuração USB e aceite a chave no aparelho." >&2
    adb devices
    exit 1
  fi
  if ((${#DEVICES[@]} > 1)); then
    echo "Mais de um telefone conectado; use adb -s SERIAL install -r $APK" >&2
    printf '%s\n' "${DEVICES[@]}"
    exit 1
  fi
  adb -s "${DEVICES[0]}" install -r "$APK"
  echo "APK instalado no dispositivo ${DEVICES[0]}"
fi
