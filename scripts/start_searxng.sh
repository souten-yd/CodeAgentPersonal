#!/usr/bin/env bash
set -u

SEARXNG_PORT="${SEARXNG_PORT:-8088}"
SEARXNG_BIND_ADDRESS="${SEARXNG_BIND_ADDRESS:-127.0.0.1}"
SEARXNG_BASE_URL="${SEARXNG_BASE_URL:-http://127.0.0.1:${SEARXNG_PORT}/}"
SEARXNG_CONFIG_DIR="${SEARXNG_CONFIG_DIR:-/workspace/ca_data/searxng}"
SEARXNG_TEMPLATE_PATH="${SEARXNG_TEMPLATE_PATH:-/app/config/searxng/settings.yml.template}"
SEARXNG_SETTINGS_PATH="${SEARXNG_SETTINGS_PATH:-${SEARXNG_CONFIG_DIR}/settings.yml}"
SEARXNG_SECRET_FILE="${SEARXNG_SECRET_FILE:-${SEARXNG_CONFIG_DIR}/secret_key}"
SEARXNG_START_TIMEOUT_SEC="${SEARXNG_START_TIMEOUT_SEC:-12}"
SEARXNG_LOG_FILE="${SEARXNG_LOG_FILE:-${SEARXNG_CONFIG_DIR}/searxng.log}"
SEARXNG_ENGINE_PROFILE="${SEARXNG_ENGINE_PROFILE:-adaptive_broad_research}"
SEARXNG_SAFE_KEEP_ONLY_ENGINES="${SEARXNG_SAFE_KEEP_ONLY_ENGINES:-wikipedia,wikidata,arxiv,crossref,openalex,semantic scholar,github,stackoverflow}"
SEARXNG_DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES:-startpage,bing,karmasearch,karmasearch videos,qwant,mojeek,yahoo}"
SEARXNG_HEALTH_ENGINE="${SEARXNG_HEALTH_ENGINE:-wikipedia}"
SEARXNG_FORCE_SAFE_SETTINGS="${SEARXNG_FORCE_SAFE_SETTINGS:-false}"
SEARXNG_HEALTH_ENGINE_ENCODED="$(HEALTH_ENGINE="${SEARXNG_HEALTH_ENGINE}" python3 - <<'PY_HEALTH_ENGINE'
from urllib.parse import quote
import os
print(quote(os.environ.get("HEALTH_ENGINE", "wikipedia"), safe=""))
PY_HEALTH_ENGINE
)"
SEARXNG_PROBE_URL="http://127.0.0.1:${SEARXNG_PORT}/search?format=json&q=healthcheck&engines=${SEARXNG_HEALTH_ENGINE_ENCODED}"
SEARXNG_REPAIR_SETTINGS="${SEARXNG_REPAIR_SETTINGS:-true}"
SEARXNG_STRICT_HEALTH="${SEARXNG_STRICT_HEALTH:-false}"
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

log "engine_profile=${SEARXNG_ENGINE_PROFILE}"
log "allow_broad_web_engines=${NEXUS_ALLOW_BROAD_WEB_ENGINES:-true}"
log "broad_web_engines=${NEXUS_BROAD_WEB_ENGINES:-google,brave,duckduckgo}"
log "safe_keep_only_engines=${SEARXNG_SAFE_KEEP_ONLY_ENGINES}"
log "disabled_engines=${SEARXNG_DISABLED_ENGINES}"
log "engines_news=${NEXUS_SEARXNG_ENGINES_NEWS:-}"
log "engines_market=${NEXUS_SEARXNG_ENGINES_MARKET:-}"
log "engines_source=${NEXUS_SEARXNG_ENGINES_SOURCE:-}"
log "health_engine=${SEARXNG_HEALTH_ENGINE}"
log "force_safe_settings=${SEARXNG_FORCE_SAFE_SETTINGS}"


_safe_research_enabled() {
  [[ ( "${SEARXNG_ENGINE_PROFILE}" == "safe_research" || "${SEARXNG_ENGINE_PROFILE}" == "safe_docs" ) && "${SEARXNG_REPAIR_SETTINGS}" == "true" ]]
}

render_searxng_settings_from_template() {
  if [[ ! -f "${SEARXNG_TEMPLATE_PATH}" ]]; then
    warn "Template not found: ${SEARXNG_TEMPLATE_PATH}"
    return 1
  fi
  local secret_key
  secret_key="$(cat "${SEARXNG_SECRET_FILE}")"
  sed \
    -e "s|__SEARXNG_BIND_ADDRESS__|${SEARXNG_BIND_ADDRESS}|g" \
    -e "s|__SEARXNG_PORT__|${SEARXNG_PORT}|g" \
    -e "s|__SEARXNG_BASE_URL__|${SEARXNG_BASE_URL}|g" \
    -e "s|__SEARXNG_SECRET_KEY__|${secret_key}|g" \
    "${SEARXNG_TEMPLATE_PATH}" > "${SEARXNG_SETTINGS_PATH}"
}

_force_safe_settings_enabled() {
  [[ "${SEARXNG_FORCE_SAFE_SETTINGS}" == "true" || "${SEARXNG_FORCE_SAFE_SETTINGS}" == "1" || "${SEARXNG_FORCE_SAFE_SETTINGS}" == "yes" || "${SEARXNG_FORCE_SAFE_SETTINGS}" == "on" ]]
}

repair_searxng_settings() {
  if ! _safe_research_enabled; then
    log "settings repair skipped (engine_profile=${SEARXNG_ENGINE_PROFILE}, repair=${SEARXNG_REPAIR_SETTINGS})"
    return 0
  fi
  if [[ ! -f "${SEARXNG_SETTINGS_PATH}" ]]; then
    return 0
  fi

  local timestamp
  timestamp="$(date -u +%Y%m%d%H%M%S)"
  if _force_safe_settings_enabled; then
    local backup_path="${SEARXNG_SETTINGS_PATH}.bak.${timestamp}"
    cp -p "${SEARXNG_SETTINGS_PATH}" "${backup_path}" || warn "failed to backup existing settings before force reset: ${SEARXNG_SETTINGS_PATH}"
    log "force safe settings reset requested; backup=${backup_path}"
    if ! render_searxng_settings_from_template; then
      warn "force safe settings reset failed; keeping startup non-fatal"
      return 0
    fi
  fi

  SETTINGS_PATH="${SEARXNG_SETTINGS_PATH}" \
  DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES}" \
  SAFE_KEEP_ONLY_ENGINES="${SEARXNG_SAFE_KEEP_ONLY_ENGINES}" \
  REPAIR_TIMESTAMP="${timestamp}" \
  SEARXNG_BIND_ADDRESS="${SEARXNG_BIND_ADDRESS}" \
  SEARXNG_PORT="${SEARXNG_PORT}" \
  SEARXNG_BASE_URL="${SEARXNG_BASE_URL}" \
  SEARXNG_SECRET_FILE="${SEARXNG_SECRET_FILE}" \
  python3 - <<'EOF_SAFE_REPAIR'
from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
from pathlib import Path

settings_path = Path(os.environ["SETTINGS_PATH"])
keep_only_engines = [item.strip() for item in os.environ.get("SAFE_KEEP_ONLY_ENGINES", "").split(",") if item.strip()]
disabled_engines = [item.strip() for item in os.environ.get("DISABLED_ENGINES", "").split(",") if item.strip()]
marker = "# CodeAgent safe_research engine overrides"
text = settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
backup_path = settings_path.with_name(settings_path.name + ".bak." + os.environ.get("REPAIR_TIMESTAMP", "manual"))

def _safe_minimal_settings() -> str:
    secret_file = Path(os.environ.get("SEARXNG_SECRET_FILE", ""))
    secret = secret_file.read_text(encoding="utf-8").strip() if secret_file.exists() else "codeagent-searxng-development-key"
    lines = [
        marker,
        "use_default_settings:",
        "  engines:",
        "    keep_only:",
        *[f"      - {engine}" for engine in keep_only_engines],
        "    remove:",
        *[f"      - {engine}" for engine in disabled_engines],
        "",
        "general:",
        '  instance_name: "CodeAgent SearXNG"',
        "",
        "search:",
        "  formats:",
        "    - html",
        "    - json",
        "",
        "server:",
        f'  bind_address: "{os.environ.get("SEARXNG_BIND_ADDRESS", "127.0.0.1")}"',
        f'  port: {os.environ.get("SEARXNG_PORT", "8088")}',
        f'  base_url: "{os.environ.get("SEARXNG_BASE_URL", "")}"',
        f'  secret_key: "{secret}"',
        "",
        "botdetection:",
        "  ip_limit:",
        "    link_token: false",
        "  ip_lists:",
        "    block_ip: []",
    ]
    return "\n".join(lines).rstrip() + "\n"

def _has_expected_yaml(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    uds = data.get("use_default_settings")
    if not isinstance(uds, dict):
        return False
    engines = uds.get("engines")
    if not isinstance(engines, dict):
        return False
    keep = engines.get("keep_only")
    remove = engines.get("remove")
    return keep == keep_only_engines and remove == disabled_engines

if importlib.util.find_spec("yaml") is not None:
    yaml = importlib.import_module("yaml")
    try:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            data = {}
        if marker in text and _has_expected_yaml(data):
            print("unchanged")
            raise SystemExit(0)
        shutil.copy2(settings_path, backup_path)
        data["use_default_settings"] = {"engines": {"keep_only": keep_only_engines, "remove": disabled_engines}}
        data.pop("engines", None)
        rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        rendered = marker + "\n" + rendered.lstrip()
        settings_path.write_text(rendered, encoding="utf-8")
        print(f"repaired yaml backup={backup_path}")
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"yaml_repair_failed={exc}; falling back to safe regeneration")

shutil.copy2(settings_path, backup_path)
settings_path.write_text(_safe_minimal_settings(), encoding="utf-8")
print(f"repaired regenerated backup={backup_path}")
EOF_SAFE_REPAIR
}

sanitize_non_safe_profile_settings() {
  if _safe_research_enabled; then
    return 0
  fi
  if [[ ! -f "${SEARXNG_SETTINGS_PATH}" ]]; then
    return 0
  fi
  SETTINGS_PATH="${SEARXNG_SETTINGS_PATH}" python3 - <<'EOF_NON_SAFE_SANITIZE'
from pathlib import Path
import os
import shutil
import re

settings_path = Path(os.environ["SETTINGS_PATH"])
text = settings_path.read_text(encoding="utf-8")
safe_marker = "# CodeAgent safe_research engine overrides"
if safe_marker not in text and "keep_only:" not in text:
    raise SystemExit(0)
timestamp = __import__("datetime").datetime.utcnow().strftime("%Y%m%d%H%M%S")
backup = settings_path.with_name(settings_path.name + f".bak.{timestamp}.adaptive")
shutil.copy2(settings_path, backup)
text = text.replace(safe_marker + "\n", "")
text = re.sub(r"(?ms)^\s*use_default_settings:\s*\n\s*engines:\s*\n\s*keep_only:\s*\n(?:\s*-\s*.*\n)+\s*remove:\s*\n(?:\s*-\s*.*\n)+", "", text).lstrip()
settings_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
print(f"sanitized existing safe settings backup={backup}")
EOF_NON_SAFE_SANITIZE
}

probe_searxng_json() {
  local probe_body="$1"
  PROBE_BODY="${probe_body}" DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES}" python3 - <<'EOF_SAFE_PROBE'
from __future__ import annotations

import json
import os
import sys

body = os.environ.get("PROBE_BODY", "")
watched = [item.strip().lower() for item in os.environ.get("DISABLED_ENGINES", "").split(",") if item.strip()]
try:
    payload = json.loads(body)
except Exception as exc:
    print(f"degraded: non-json SearXNG response: {exc}")
    sys.exit(2)
if not isinstance(payload, dict):
    print("degraded: SearXNG JSON response is not an object")
    sys.exit(2)
results = payload.get("results")
if not isinstance(results, list):
    print("degraded: SearXNG JSON response has no results array")
    sys.exit(2)
errors = payload.get("errors") or []
if errors:
    lowered = json.dumps(errors, ensure_ascii=False).lower()
    watched_hits = [engine for engine in watched if engine in lowered]
    if watched_hits or "captcha" in lowered or "jsondecode" in lowered or "jsondecodeerror" in lowered:
        print("degraded: CAPTCHA/non-JSON prone engine errors in SearXNG response: " + ",".join(watched_hits or ["unknown"]))
        sys.exit(3)
    print("degraded: SearXNG response contains engine errors")
    sys.exit(3)
print("ok")
EOF_SAFE_PROBE
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
  render_searxng_settings_from_template || {
      warn "Failed to render settings template"
      set_autostart_status "failed_render_settings" "SearXNG設定テンプレートの展開に失敗しました。"
      exit 0
    }
fi

if ! repair_searxng_settings; then
  warn "settings repair failed; continuing startup with existing settings: ${SEARXNG_SETTINGS_PATH}"
else
  log "settings repair completed or not needed: ${SEARXNG_SETTINGS_PATH}"
fi

sanitize_non_safe_profile_settings || warn "failed to sanitize safe marker for non-safe profile; continuing"

if command -v curl >/dev/null 2>&1; then
  existing_probe_body="$(curl -fsS --max-time 2 "${SEARXNG_PROBE_URL}" 2>/dev/null || true)"
  if [[ -n "${existing_probe_body}" ]]; then
    existing_probe_message="$(probe_searxng_json "${existing_probe_body}" 2>&1)"
    existing_probe_code=$?
    if (( existing_probe_code == 0 )); then
      log "SearXNG is already responding: ${SEARXNG_PROBE_URL}"
      set_autostart_status "ready_existing" "SearXNGは既に起動済みです: ${SEARXNG_PROBE_URL}"
    elif [[ "${SEARXNG_STRICT_HEALTH}" == "true" ]]; then
      warn "Existing SearXNG health probe degraded: ${existing_probe_message}"
      set_autostart_status "failed_degraded" "SearXNGは起動済みですが検索品質probeがdegradedです: ${existing_probe_message}"
    else
      warn "Existing SearXNG health probe degraded: ${existing_probe_message}"
      set_autostart_status "ready_degraded" "SearXNGは起動済みですが検索品質probeがdegradedです: ${existing_probe_message}"
    fi
    exit 0
  fi
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
  probe_body=""
  until probe_body="$(curl -fsS --max-time 2 "${SEARXNG_PROBE_URL}" 2>/dev/null)"; do
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
    probe_message="$(probe_searxng_json "${probe_body}" 2>&1)"
    probe_code=$?
    if (( probe_code == 0 )); then
      log "Health probe succeeded: ${SEARXNG_PROBE_URL}"
      set_autostart_status "ready" "SearXNG起動確認に成功しました: ${SEARXNG_PROBE_URL}"
    else
      warn "Health probe degraded: ${probe_message}"
      if [[ "${SEARXNG_STRICT_HEALTH}" == "true" ]]; then
        set_autostart_status "failed_degraded" "SearXNGは応答しましたが検索品質probeがdegradedです: ${probe_message}"
      else
        set_autostart_status "ready_degraded" "SearXNGは応答しましたが検索品質probeがdegradedです: ${probe_message}"
      fi
    fi
  fi
else
  warn "curl not found; skipping health probe."
  set_autostart_status "started_unverified" "curl未導入のためSearXNGのヘルスチェックをスキップしました。"
fi

exit 0
