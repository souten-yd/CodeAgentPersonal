from __future__ import annotations

from pathlib import Path

import yaml

from scripts.start_searxng_windows import ensure_settings, repair_safe_research_settings, validate_settings_secret_key


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_windows_secret_file_random_but_settings_missing_server_gets_synced(tmp_path: Path) -> None:
    config_dir = tmp_path / "searxng"
    config_dir.mkdir(parents=True)
    (config_dir / "secret_key").write_text("random-secret\n", encoding="utf-8")
    (config_dir / "settings.yml").write_text(
        "# CodeAgent safe_research engine overrides\nuse_default_settings:\n  engines:\n    keep_only:\n      - wikipedia\n    remove:\n      - duckduckgo\n",
        encoding="utf-8",
    )

    ensure_settings(config_dir, env={"SEARXNG_ENGINE_PROFILE": "safe_research", "SEARXNG_REPAIR_SETTINGS": "true"})
    data = _read_yaml(config_dir / "settings.yml")
    assert data["server"]["secret_key"] == "random-secret"
    assert "json" in data["search"]["formats"]


def test_windows_settings_ultrasecretkey_replaced(tmp_path: Path) -> None:
    config_dir = tmp_path / "searxng"
    config_dir.mkdir(parents=True)
    (config_dir / "secret_key").write_text("random-secret\n", encoding="utf-8")
    (config_dir / "settings.yml").write_text('server:\n  secret_key: "ultrasecretkey"\n', encoding="utf-8")

    ensure_settings(config_dir)
    text = (config_dir / "settings.yml").read_text(encoding="utf-8")
    assert "ultrasecretkey" not in text
    assert "random-secret" in text


def test_windows_existing_custom_secret_preserved(tmp_path: Path) -> None:
    config_dir = tmp_path / "searxng"
    config_dir.mkdir(parents=True)
    (config_dir / "secret_key").write_text("file-secret\n", encoding="utf-8")
    (config_dir / "settings.yml").write_text('server:\n  secret_key: "custom-secret"\n', encoding="utf-8")

    ensure_settings(config_dir)
    text = (config_dir / "settings.yml").read_text(encoding="utf-8")
    assert "custom-secret" in text
    assert "ultrasecretkey" not in text


def test_windows_safe_research_repair_preserves_or_restores_server_secret(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yml"
    log_file = tmp_path / "searxng.log"
    settings_file.write_text('server:\n  secret_key: "custom-secret"\nengines:\n  - google\n', encoding="utf-8")
    repair_safe_research_settings(settings_file, ["google"], ["wikipedia"], log_file)
    assert _read_yaml(settings_file)["server"]["secret_key"] == "custom-secret"


def test_windows_secret_value_not_logged(tmp_path: Path) -> None:
    config_dir = tmp_path / "searxng"
    config_dir.mkdir(parents=True)
    secret = "random-secret"
    (config_dir / "secret_key").write_text(secret + "\n", encoding="utf-8")
    (config_dir / "settings.yml").write_text("use_default_settings:\n  engines: {}\n", encoding="utf-8")
    log_file = config_dir / "searxng.log"

    ensure_settings(config_dir, log_file=log_file)
    assert secret not in log_file.read_text(encoding="utf-8")


def test_windows_validate_settings_secret_key_blocks_missing(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.yml"
    settings_file.write_text("search:\n  formats:\n    - json\n", encoding="utf-8")
    ok, reason = validate_settings_secret_key(settings_file)
    assert ok is False
    assert reason == "secret_key_missing"
