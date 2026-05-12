from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "searxng" / "settings.yml.template"
START_SCRIPT = ROOT / "scripts" / "start_searxng.sh"
RUNPOD_START = ROOT / "scripts" / "runpod_start.sh"
WINDOWS_START = ROOT / "scripts" / "start_searxng_windows.py"
WEB_SCOUT = ROOT / "app" / "nexus" / "web_scout.py"

OBSERVED_BAD_ENGINES = ("duckduckgo", "startpage", "google", "bing", "brave", "karmasearch")
EXPANDED_BAD_ENGINES = (*OBSERVED_BAD_ENGINES, "karmasearch videos", "qwant", "mojeek", "yahoo")
SAFE_KEEP_ONLY_ENGINES = ("wikipedia", "wikidata", "arxiv", "crossref", "openalex", "semantic scholar", "github", "stackoverflow")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _keep_only_block(text: str) -> str:
    match = re.search(r"(?ms)^\s*keep_only:\s*\n(?P<body>(?:^\s+-\s+.*\n?)+?)^\s*remove:", text)
    assert match, "settings template must declare use_default_settings.engines.keep_only"
    return match.group("body").lower()


def test_template_uses_keep_only_for_safe_profile() -> None:
    text = _read(TEMPLATE)
    assert "use_default_settings:" in text
    assert "keep_only:" in text
    assert "remove:" in text
    keep_only = _keep_only_block(text)
    for engine in SAFE_KEEP_ONLY_ENGINES:
        assert f"- {engine}" in keep_only
    for engine in OBSERVED_BAD_ENGINES:
        assert f"- {engine}" not in keep_only


def test_disabled_list_includes_observed_bad_engines() -> None:
    text = _read(START_SCRIPT)
    assert "SEARXNG_DISABLED_ENGINES" in text
    for engine in EXPANDED_BAD_ENGINES:
        assert engine in text


def test_health_probe_uses_safe_engine() -> None:
    text = _read(START_SCRIPT)
    assert "SEARXNG_HEALTH_ENGINE" in text
    assert "SEARXNG_PROBE_URL" in text
    assert "engines=${SEARXNG_HEALTH_ENGINE_ENCODED}" in text


def test_force_safe_settings_exists() -> None:
    text = _read(START_SCRIPT)
    assert "SEARXNG_FORCE_SAFE_SETTINGS" in text
    assert "force safe settings reset" in text
    assert ".bak." in text
    assert "render_searxng_settings_from_template" in text


def test_web_scout_supports_engine_param() -> None:
    text = _read(WEB_SCOUT)
    assert "NEXUS_SEARXNG_ENGINES" in text
    assert 'query_params["engines"]' in text
    assert "parse.urlencode(query_params)" in text
    assert "SEARXNG_SAFE_KEEP_ONLY_ENGINES" in text


def test_windows_repair_supports_keep_only() -> None:
    text = _read(WINDOWS_START)
    assert "keep_only" in text
    assert "SEARXNG_FORCE_SAFE_SETTINGS" in text
    assert "DEFAULT_SAFE_KEEP_ONLY_ENGINES" in text
    for engine in EXPANDED_BAD_ENGINES:
        assert engine in text


def test_start_script_declares_safe_research_profile() -> None:
    text = _read(START_SCRIPT)
    assert 'SEARXNG_ENGINE_PROFILE="${SEARXNG_ENGINE_PROFILE:-safe_research}"' in text
    assert 'SEARXNG_SAFE_KEEP_ONLY_ENGINES="${SEARXNG_SAFE_KEEP_ONLY_ENGINES:-wikipedia,wikidata,arxiv,crossref,openalex,semantic scholar,github,stackoverflow}"' in text
    assert 'SEARXNG_REPAIR_SETTINGS="${SEARXNG_REPAIR_SETTINGS:-true}"' in text
    assert 'SEARXNG_STRICT_HEALTH="${SEARXNG_STRICT_HEALTH:-false}"' in text
    assert 'log "engine_profile=${SEARXNG_ENGINE_PROFILE}"' in text


def test_start_script_repairs_existing_settings() -> None:
    text = _read(START_SCRIPT)
    assert "repair_searxng_settings()" in text
    assert "# CodeAgent safe_research engine overrides" in text
    assert "use_default_settings" in text
    assert "keep_only" in text
    assert "remove" in text
    assert "shutil.copy2(settings_path, backup_path)" in text


def test_start_script_has_json_degraded_health_probe() -> None:
    text = _read(START_SCRIPT)
    assert "probe_searxng_json()" in text
    assert "ready_degraded" in text
    assert "failed_degraded" in text
    assert "CAPTCHA/non-JSON prone engine errors" in text


def test_runpod_start_logs_engine_profile() -> None:
    text = _read(RUNPOD_START)
    assert 'export SEARXNG_ENGINE_PROFILE="${SEARXNG_ENGINE_PROFILE:-adaptive_broad_research}"' in text
    assert 'echo "[Runpod] SEARXNG_ENGINE_PROFILE=${SEARXNG_ENGINE_PROFILE}"' in text
    assert 'export SEARXNG_SAFE_KEEP_ONLY_ENGINES=' in text
    assert 'export SEARXNG_DISABLED_ENGINES=' in text
    assert 'google' not in re.search(r'export SEARXNG_DISABLED_ENGINES="\$\{SEARXNG_DISABLED_ENGINES:-([^}]*)\}"', text).group(1)
    assert 'brave' not in re.search(r'export SEARXNG_DISABLED_ENGINES="\$\{SEARXNG_DISABLED_ENGINES:-([^}]*)\}"', text).group(1)
    assert 'duckduckgo' not in re.search(r'export SEARXNG_DISABLED_ENGINES="\$\{SEARXNG_DISABLED_ENGINES:-([^}]*)\}"', text).group(1)
    assert 'export NEXUS_ALLOW_BROAD_WEB_ENGINES=' in text
    assert 'export NEXUS_BROAD_WEB_ENGINES=' in text
    assert 'export SEARXNG_HEALTH_ENGINE=' in text
    assert 'export SEARXNG_FORCE_SAFE_SETTINGS=' in text


def test_web_scout_has_searxng_degraded_diagnostics() -> None:
    text = _read(WEB_SCOUT)
    assert 'searxng_engine_captcha_or_non_json' in text
    assert 'web_search_provider_degraded' in text
    assert 'Disable CAPTCHA-prone engines or use safe_research profile' in text
    assert 'provider_status"' in text
    assert 'diagnostics"' in text
