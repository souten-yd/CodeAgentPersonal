from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_forge_arena_ui import FORGE_JS, _NODE_TEMPLATE


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "ui.html").read_text(encoding="utf-8")
JS = FORGE_JS.read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")


def _render(tmp_path, payload: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "advanced_twin.js"
    script.write_text(
        _NODE_TEMPLATE.replace(
            "process.stdout.write(global.window.Forge._arenaHtml(JSON.parse(process.argv[3])));",
            "process.stdout.write(global.window.Forge._twinAdvancedHtml(JSON.parse(process.argv[3])));",
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [node, str(script), str(FORGE_JS), json.dumps(payload)], capture_output=True,
        text=True, timeout=30, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_advanced_renders_twin_settings_profiles_and_read_only_inspectors(tmp_path):
    html = _render(tmp_path, {
        "twinSettings": {"settings": {"mode": "shadow", "block_schema": True}, "reversible": True},
        "twinProfiles": {"profiles": [{"model_id": "local", "provider_id": "anvil", "sample_count": 2}]},
    })
    assert "Twin Settings" in html and "mode" in html and "shadow" in html
    assert "local" in html and "anvil" in html
    assert "Read-only Twin Inspector" in html
    assert "data-twin-context-form" in html and "data-twin-impact-form" in html
    assert "No apply or execute action is exposed" in html


def test_advanced_uses_forge_twin_facade_and_has_no_inspector_apply_path():
    assert "api('/twin/settings')" in JS
    assert "api('/twin/profiles')" in JS
    assert "'/twin/inspect/context'" in JS
    assert "'/twin/inspect/impact'" in JS
    assert "/twin/inspect/apply" not in JS
    assert "/twin/inspect/execute" not in JS


def test_independent_twin_tab_hidden_without_deleting_legacy_inspector():
    assert 'id="forge-subtab-twin"' in UI and 'hidden aria-hidden="true">Twin</button>' in UI
    assert 'id="tab-twin"' in UI
    assert "function renderTwinPanel" in UI


def test_mobile_twin_inspector_collapses_to_one_column():
    assert "@media(max-width:600px){.forge-twin-inspector-grid{grid-template-columns:1fr}" in CSS
