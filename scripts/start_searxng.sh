#!/usr/bin/env bash
set -u

SEARXNG_PORT="${SEARXNG_PORT:-8088}"
SEARXNG_BIND_ADDRESS="${SEARXNG_BIND_ADDRESS:-127.0.0.1}"
SEARXNG_BASE_URL="${SEARXNG_BASE_URL:-http://127.0.0.1:${SEARXNG_PORT}/}"
SEARXNG_CONFIG_DIR="${SEARXNG_CONFIG_DIR:-/workspace/ca_data/searxng}"
SEARXNG_TEMPLATE_PATH="${SEARXNG_TEMPLATE_PATH:-/app/config/searxng/settings.yml.template}"
SEARXNG_SETTINGS_PATH="${SEARXNG_SETTINGS_PATH:-${SEARXNG_CONFIG_DIR}/settings.yml}"
SEARXNG_SECRET_FILE="${SEARXNG_SECRET_FILE:-${SEARXNG_CONFIG_DIR}/secret_key}"
SEARXNG_PROBE_URL="http://127.0.0.1:${SEARXNG_PORT}/search?format=json&q=healthcheck"
SEARXNG_START_TIMEOUT_SEC="${SEARXNG_START_TIMEOUT_SEC:-12}"
SEARXNG_LOG_FILE="${SEARXNG_LOG_FILE:-${SEARXNG_CONFIG_DIR}/searxng.log}"
SEARXNG_PYTHON="${SEARXNG_PYTHON:-/opt/searxng/searx-pyenv/bin/python}"
SEARXNG_SRC="${SEARXNG_SRC:-/opt/searxng/searxng-src}"
STATUS_OUTPUT_FILE="${RUNPOD_SEARXNG_STATUS_OUTPUT_FILE:-}"
RUNPOD_SEARXNG_AUTOSTART_STATUS="${RUNPOD_SEARXNG_AUTOSTART_STATUS:-not_requested}"
RUNPOD_SEARXNG_AUTOSTART_HINT="${RUNPOD_SEARXNG_AUTOSTART_HINT:-}"

log() {
  echo "[Runpod][SearXNG] $*"
}

warn() {
  echo "[Runpod][SearXNG][WARN] $*" >&2
}

err() {
  echo "[Runpod][SearXNG][ERROR] $*" >&2
}

set_autostart_status() {
  RUNPOD_SEARXNG_AUTOSTART_STATUS="$1"
  RUNPOD_SEARXNG_AUTOSTART_HINT="${2:-}"
  export RUNPOD_SEARXNG_AUTOSTART_STATUS
  export RUNPOD_SEARXNG_AUTOSTART_HINT
  if [[ -n "${STATUS_OUTPUT_FILE}" ]]; then
    cat > "${STATUS_OUTPUT_FILE}" <<EOF
RUNPOD_SEARXNG_AUTOSTART_STATUS='${RUNPOD_SEARXNG_AUTOSTART_STATUS}'
RUNPOD_SEARXNG_AUTOSTART_HINT='${RUNPOD_SEARXNG_AUTOSTART_HINT//\'/\"}'
EOF
  fi
}

mkdir -p "${SEARXNG_CONFIG_DIR}" || {
  warn "Failed to create config dir: ${SEARXNG_CONFIG_DIR}"
  set_autostart_status "failed_config_dir" "SearXNG設定ディレクトリを作成できませんでした: ${SEARXNG_CONFIG_DIR}"
  exit 0
}

if [[ ! -f "${SEARXNG_SECRET_FILE}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY' > "${SEARXNG_SECRET_FILE}" 2>/dev/null || true
import secrets
print(secrets.token_hex(32))
PY
  fi
fi

if [[ ! -s "${SEARXNG_SECRET_FILE}" ]]; then
  warn "Failed to generate secret with python3. Falling back to static development key."
  echo "codeagent-searxng-development-key" > "${SEARXNG_SECRET_FILE}"
fi

if [[ ! -f "${SEARXNG_SETTINGS_PATH}" ]]; then
  if [[ ! -f "${SEARXNG_TEMPLATE_PATH}" ]]; then
    warn "Template not found: ${SEARXNG_TEMPLATE_PATH}"
    set_autostart_status "failed_missing_template" "SearXNG設定テンプレートが見つかりませんでした: ${SEARXNG_TEMPLATE_PATH}"
    exit 0
  fi

  log "Initializing config from template: ${SEARXNG_TEMPLATE_PATH} -> ${SEARXNG_SETTINGS_PATH}"
  secret_key="$(cat "${SEARXNG_SECRET_FILE}")"
  sed \
    -e "s|__SEARXNG_BIND_ADDRESS__|${SEARXNG_BIND_ADDRESS}|g" \
    -e "s|__SEARXNG_PORT__|${SEARXNG_PORT}|g" \
    -e "s|__SEARXNG_BASE_URL__|${SEARXNG_BASE_URL}|g" \
    -e "s|__SEARXNG_SECRET_KEY__|${secret_key}|g" \
    "${SEARXNG_TEMPLATE_PATH}" > "${SEARXNG_SETTINGS_PATH}" || {
      warn "Failed to render settings template"
      set_autostart_status "failed_render_settings" "SearXNG設定テンプレートの展開に失敗しました。"
      exit 0
    }
fi

if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "${SEARXNG_PROBE_URL}" >/dev/null 2>&1; then
  log "SearXNG is already responding: ${SEARXNG_PROBE_URL}"
  set_autostart_status "ready_existing" "SearXNGは既に起動済みです: ${SEARXNG_PROBE_URL}"
  exit 0
fi

START_CMD=""
if [[ -x "${SEARXNG_PYTHON}" && -f "${SEARXNG_SRC}/searx/webapp.py" ]]; then
  START_CMD="cd ${SEARXNG_SRC} && ${SEARXNG_PYTHON} searx/webapp.py"
elif command -v searxng-run >/dev/null 2>&1; then
  START_CMD="searxng-run"
elif python -c "import searx" >/dev/null 2>&1; then
  START_CMD="python -m searx.webapp"
else
  warn "SearXNG runtime command not found (${SEARXNG_PYTHON} + ${SEARXNG_SRC}/searx/webapp.py / searxng-run / python -m searx.webapp)."
  set_autostart_status "failed_runtime_missing" "imageにruntime未導入のため、SearXNG実行コマンド(${SEARXNG_PYTHON} + ${SEARXNG_SRC}/searx/webapp.py / searxng-run / python -m searx.webapp)が見つかりません。"
  exit 0
fi

log "Starting local SearXNG process (${START_CMD})"
SEARXNG_SETTINGS_PATH="${SEARXNG_SETTINGS_PATH}" nohup bash -lc "${START_CMD}" >> "${SEARXNG_LOG_FILE}" 2>&1 &

if command -v curl >/dev/null 2>&1; then
  elapsed=0
  until curl -fsS --max-time 2 "${SEARXNG_PROBE_URL}" >/dev/null 2>&1; do
    if (( elapsed >= SEARXNG_START_TIMEOUT_SEC )); then
      warn "Health probe failed: ${SEARXNG_PROBE_URL}"
      warn "See logs: ${SEARXNG_LOG_FILE}"
      set_autostart_status "failed_timeout" "SearXNGの起動確認がタイムアウトしました。ログを確認してください: ${SEARXNG_LOG_FILE}"
      break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  if (( elapsed < SEARXNG_START_TIMEOUT_SEC )); then
    log "Health probe succeeded: ${SEARXNG_PROBE_URL}"
    set_autostart_status "ready" "SearXNG起動確認に成功しました: ${SEARXNG_PROBE_URL}"
  fi
else
  warn "curl not found; skipping health probe."
  set_autostart_status "started_unverified" "curl未導入のためSearXNGのヘルスチェックをスキップしました。"
fi

exit 0
