from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = ROOT / "scripts" / "start_searxng.sh"


def test_runpod_safe_minimal_settings_contains_server_secret() -> None:
    text = START_SCRIPT.read_text(encoding="utf-8")
    assert "_safe_minimal_settings()" in text
    assert "server:" in text
    assert "secret_key:" in text


def test_runpod_validation_checks_server_secret_missing() -> None:
    text = START_SCRIPT.read_text(encoding="utf-8")
    assert "server.secret_key missing" in text


def test_runpod_script_does_not_use_ultrasecretkey() -> None:
    text = START_SCRIPT.read_text(encoding="utf-8")
    assert "ultrasecretkey" not in text
