from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = ROOT / "scripts" / "start_searxng.sh"
DOCKER_START = ROOT / "docker" / "start-services.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_adaptive_missing_settings_initializes_from_template() -> None:
    text = _read(START_SCRIPT)
    assert "ensure_profile_settings()" in text
    assert "profile settings missing; generating from template" in text


def test_adaptive_safe_marker_or_keep_only_triggers_backup_and_regenerate() -> None:
    text = _read(START_SCRIPT)
    assert "profile marker mismatch or missing; backup=" in text
    assert "use_default_settings.engines.keep_only exists" in text
    assert ".bak." in text and ".invalid" in text


def test_adaptive_missing_json_format_triggers_regenerate() -> None:
    text = _read(START_SCRIPT)
    assert "search.formats missing json" in text


def test_adaptive_missing_server_port_triggers_regenerate() -> None:
    text = _read(START_SCRIPT)
    assert "server.port missing" in text


def test_adaptive_profile_does_not_sanitize_keep_only_inline() -> None:
    text = _read(START_SCRIPT)
    assert "sanitize_non_safe_profile_settings" not in text
    assert "use_default_settings.engines.keep_only exists" in text


def test_start_timeout_default_is_30_seconds() -> None:
    text = _read(START_SCRIPT)
    assert 'SEARXNG_START_TIMEOUT_SEC="${SEARXNG_START_TIMEOUT_SEC:-30}"' in text


def test_disabled_engines_default_contains_required_engines() -> None:
    text = _read(START_SCRIPT)
    assert 'SEARXNG_DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES:-startpage,karmasearch,karmasearch videos,qwant,yahoo}"' in text


def test_docker_broad_engines_default_contains_google_bing_brave_duckduckgo() -> None:
    text = _read(DOCKER_START)
    assert 'export NEXUS_BROAD_WEB_ENGINES="${NEXUS_BROAD_WEB_ENGINES:-google,bing,brave,duckduckgo}"' in text
