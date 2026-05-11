from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "searxng" / "settings.yml.template"
START_SCRIPT = ROOT / "scripts" / "start_searxng.sh"
RUNPOD_START = ROOT / "scripts" / "runpod_start.sh"
WINDOWS_START = ROOT / "scripts" / "start_searxng_windows.py"
WEB_SCOUT = ROOT / "app" / "nexus" / "web_scout.py"

CAPTCHA_PRONE_ENGINES = ("duckduckgo", "startpage", "google", "bing")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _engine_disabled(text: str, engine: str) -> bool:
    return bool(
        re.search(
            r"(?ms)^\s*-\s*name:\s*['\"]?" + re.escape(engine) + r"['\"]?\s*$.*?^\s*disabled:\s*true\s*$",
            text,
        )
    )


def test_template_disables_captcha_prone_engines() -> None:
    text = _read(TEMPLATE)
    assert "use_default_settings: true" in text
    assert "formats:" in text and "json" in text
    for engine in CAPTCHA_PRONE_ENGINES:
        assert _engine_disabled(text, engine), f"{engine} must be disabled in template"


def test_start_script_declares_safe_research_profile() -> None:
    text = _read(START_SCRIPT)
    assert 'SEARXNG_ENGINE_PROFILE="${SEARXNG_ENGINE_PROFILE:-safe_research}"' in text
    assert 'SEARXNG_DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES:-duckduckgo,startpage,google,bing}"' in text
    assert 'SEARXNG_REPAIR_SETTINGS="${SEARXNG_REPAIR_SETTINGS:-true}"' in text
    assert 'SEARXNG_STRICT_HEALTH="${SEARXNG_STRICT_HEALTH:-false}"' in text
    assert 'log "engine_profile=${SEARXNG_ENGINE_PROFILE}"' in text


def test_start_script_repairs_existing_settings() -> None:
    text = _read(START_SCRIPT)
    assert "repair_searxng_settings()" in text
    assert "# CodeAgent safe_research engine overrides" in text
    assert ".bak." in text
    assert "shutil.copy2(settings_path, backup_path)" in text
    assert "DISABLED_ENGINES" in text


def test_start_script_has_json_degraded_health_probe() -> None:
    text = _read(START_SCRIPT)
    assert "probe_searxng_json()" in text
    assert "ready_degraded" in text
    assert "failed_degraded" in text
    assert "CAPTCHA/non-JSON prone engine errors" in text


def test_runpod_start_logs_engine_profile() -> None:
    text = _read(RUNPOD_START)
    assert 'export SEARXNG_ENGINE_PROFILE="${SEARXNG_ENGINE_PROFILE:-safe_research}"' in text
    assert 'echo "[Runpod] SEARXNG_ENGINE_PROFILE=${SEARXNG_ENGINE_PROFILE}"' in text
    assert 'export SEARXNG_DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES:-duckduckgo,startpage,google,bing}"' in text
    assert 'export SEARXNG_REPAIR_SETTINGS="${SEARXNG_REPAIR_SETTINGS:-true}"' in text


def test_windows_startup_has_safe_engine_repair() -> None:
    text = _read(WINDOWS_START)
    assert 'DEFAULT_DISABLED_ENGINES = "duckduckgo,startpage,google,bing"' in text
    assert 'env.get("SEARXNG_ENGINE_PROFILE", "safe_research")' in text
    assert "repair_safe_research_settings" in text
    assert "safe_research settings repaired" in text
    assert ".bak." in text


def test_web_scout_has_searxng_degraded_diagnostics() -> None:
    text = _read(WEB_SCOUT)
    assert 'searxng_engine_captcha_or_non_json' in text
    assert 'web_search_provider_degraded' in text
    assert 'Disable CAPTCHA-prone engines or use safe_research profile' in text
    assert 'provider_status"' in text
    assert 'diagnostics"' in text
