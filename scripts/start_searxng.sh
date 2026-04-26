#!/usr/bin/env bash
set -u

SEARXNG_PORT="${SEARXNG_PORT:-8088}"
SEARXNG_BASE_URL="${SEARXNG_BASE_URL:-http://127.0.0.1:${SEARXNG_PORT}/}"
SEARXNG_CONFIG_DIR="${SEARXNG_CONFIG_DIR:-/workspace/ca_data/searxng}"
SEARXNG_IMAGE="${SEARXNG_IMAGE:-searxng/searxng:latest}"
SEARXNG_CONTAINER_NAME="${SEARXNG_CONTAINER_NAME:-codeagent_searxng}"
SEARXNG_PROBE_URL="http://127.0.0.1:${SEARXNG_PORT}/search?format=json&q=healthcheck"
SEARXNG_START_TIMEOUT_SEC="${SEARXNG_START_TIMEOUT_SEC:-12}"

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

if [[ ! -f "${SEARXNG_CONFIG_DIR}/settings.yml" ]]; then
  log "Initializing config dir: ${SEARXNG_CONFIG_DIR}"
  cat > "${SEARXNG_CONFIG_DIR}/settings.yml" <<YAML
use_default_settings: true
server:
  bind_address: 0.0.0.0
  port: ${SEARXNG_PORT}
  secret_key: "$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
YAML
fi

if ! command -v docker >/dev/null 2>&1; then
  err "docker command not found; skipping SearXNG start."
  exit 0
fi

if ! docker info >/dev/null 2>&1; then
  err "docker daemon is not available; skipping SearXNG start."
  exit 0
fi

if docker ps -a --format '{{.Names}}' | grep -Fxq "${SEARXNG_CONTAINER_NAME}"; then
  if ! docker start "${SEARXNG_CONTAINER_NAME}" >/dev/null 2>&1; then
    err "Failed to start existing container: ${SEARXNG_CONTAINER_NAME}"
    exit 0
  fi
  log "Started existing container: ${SEARXNG_CONTAINER_NAME}"
else
  if ! docker run -d \
      --name "${SEARXNG_CONTAINER_NAME}" \
      -p "127.0.0.1:${SEARXNG_PORT}:8080" \
      -e "BASE_URL=${SEARXNG_BASE_URL}" \
      -v "${SEARXNG_CONFIG_DIR}:/etc/searxng" \
      "${SEARXNG_IMAGE}" >/dev/null; then
    err "Failed to launch SearXNG container image ${SEARXNG_IMAGE}"
    exit 0
  fi
  log "Started new container: ${SEARXNG_CONTAINER_NAME}"
fi

if command -v curl >/dev/null 2>&1; then
  elapsed=0
  until curl -fsS --max-time 2 "${SEARXNG_PROBE_URL}" >/dev/null 2>&1; do
    if (( elapsed >= SEARXNG_START_TIMEOUT_SEC )); then
      warn "Health probe failed: ${SEARXNG_PROBE_URL}"
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
