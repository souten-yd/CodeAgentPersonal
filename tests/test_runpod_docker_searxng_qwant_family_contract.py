from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "searxng" / "settings.yml.template"
START_SCRIPT = ROOT / "scripts" / "start_searxng.sh"
DOCKER_START = ROOT / "docker" / "start-services.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_template_remove_list_contains_qwant_family() -> None:
    text = _read(TEMPLATE)
    for name in ["qwant", "qwant images", "qwant news", "qwant videos", "qwant web"]:
        assert f"- {name}" in text


def test_start_script_default_disabled_engines_contains_qwant_family() -> None:
    text = _read(START_SCRIPT)
    assert 'SEARXNG_DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES:-startpage,karmasearch,karmasearch videos,qwant,qwant images,qwant news,qwant videos,qwant web,yahoo}"' in text


def test_docker_start_default_disabled_engines_contains_qwant_family() -> None:
    text = _read(DOCKER_START)
    assert 'export SEARXNG_DISABLED_ENGINES="${SEARXNG_DISABLED_ENGINES:-startpage,karmasearch,karmasearch videos,qwant,qwant images,qwant news,qwant videos,qwant web,yahoo}"' in text


def test_adaptive_validation_rejects_qwant_without_family() -> None:
    text = _read(START_SCRIPT)
    assert 'qwant family remove entries missing:' in text


def test_health_probe_timeout_without_process_sets_failed_process_exited() -> None:
    text = _read(START_SCRIPT)
    assert 'failed_process_exited' in text
    assert 'SearXNG process exited before health probe' in text


def test_keyerror_qwant_hint_is_present() -> None:
    text = _read(START_SCRIPT)
    assert "KeyError: 'qwant'" in text
