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

log() {
  echo "[Runpod][SearXNG] $*"
}

warn() {
  echo "[Runpod][SearXNG][WARN] $*" >&2
}

err() {
  echo "[Runpod][SearXNG][ERROR] $*" >&2
}

mkdir -p "${SEARXNG_CONFIG_DIR}" || {
  err "Failed to create config dir: ${SEARXNG_CONFIG_DIR}"
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
    err "Template not found: ${SEARXNG_TEMPLATE_PATH}"
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
      err "Failed to render settings template"
      exit 0
    }
fi

if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 2 "${SEARXNG_PROBE_URL}" >/dev/null 2>&1; then
  log "SearXNG is already responding: ${SEARXNG_PROBE_URL}"
  exit 0
fi

START_CMD=""
if command -v searxng-run >/dev/null 2>&1; then
  START_CMD="searxng-run"
elif python -c "import searx" >/dev/null 2>&1; then
  START_CMD="python -m searx.webapp"
else
  err "SearXNG runtime command not found (searxng-run / python -m searx.webapp)."
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
      break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  if (( elapsed < SEARXNG_START_TIMEOUT_SEC )); then
    log "Health probe succeeded: ${SEARXNG_PROBE_URL}"
  fi
else
  warn "curl not found; skipping health probe."
fi

exit 0
