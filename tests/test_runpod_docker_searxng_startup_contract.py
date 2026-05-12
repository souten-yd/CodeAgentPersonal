from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER_START = ROOT / "docker" / "start-services.sh"
START_SCRIPT = ROOT / "scripts" / "start_searxng.sh"
WEB_SCOUT = ROOT / "app" / "nexus" / "web_scout.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_docker_start_defaults_to_adaptive_broad_profile() -> None:
    text = _read(DOCKER_START)
    assert 'export SEARXNG_ENGINE_PROFILE="${SEARXNG_ENGINE_PROFILE:-adaptive_broad_research}"' in text
    assert 'export NEXUS_ALLOW_BROAD_WEB_ENGINES="${NEXUS_ALLOW_BROAD_WEB_ENGINES:-true}"' in text
    assert 'export NEXUS_BROAD_WEB_ENGINES="${NEXUS_BROAD_WEB_ENGINES:-google,brave,duckduckgo}"' in text


def test_start_script_adaptive_defaults_do_not_disable_google_family() -> None:
    text = _read(START_SCRIPT)
    assert 'SEARXNG_ENGINE_PROFILE="${SEARXNG_ENGINE_PROFILE:-adaptive_broad_research}"' in text
    disabled_line = 'SEARXNG_DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES:-startpage,bing,karmasearch,karmasearch videos,qwant,mojeek,yahoo}"'
    assert disabled_line in text
    assert "google" not in disabled_line
    assert "brave" not in disabled_line
    assert "duckduckgo" not in disabled_line


def test_start_script_safe_profile_still_repairs_keep_only() -> None:
    text = _read(START_SCRIPT)
    assert '_safe_research_enabled()' in text
    assert 'safe_research' in text and 'safe_docs' in text
    assert 'keep_only' in text
    assert 'sanitize_non_safe_profile_settings()' in text


def test_web_status_reports_broad_flags_and_profile() -> None:
    text = _read(WEB_SCOUT)
    assert '"searxng_engine_profile": os.getenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research")' in text
    assert '"broad_web_enabled": broad_enabled' in text
    assert '"broad_web_engines": [e for e in engines if e.lower() in _BROAD_WEB_ENGINES]' in text
