"""PFH-2 Forge Settings UI render tests."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORGE_JS = ROOT / "web" / "js" / "forge.js"

_NODE_TEMPLATE = r"""
const fs = require('fs');
const store = {};
function mkEl(){ return { _html:'', set innerHTML(v){this._html=v;}, get innerHTML(){return this._html;},
  textContent:'', classList:{toggle(){},add(){},remove(){}}, addEventListener(){},
  querySelectorAll(){return [];}, querySelector(){return null;}, appendChild(){}, getAttribute(){return '';} }; }
global.document = { getElementById:(id)=>store[id]||(store[id]=mkEl()),
  createElement:()=>mkEl(), body:{appendChild(){}}, addEventListener(){} };
global.window = {};
global.fetch = () => Promise.reject(new Error('no-net'));
eval(fs.readFileSync(process.argv[2], 'utf8'));
const F = global.window.Forge;
const input = JSON.parse(process.argv[3]);
process.stdout.write(F._settingsHtml(input.data));
"""


def _render(tmp_path: Path, payload: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "settings.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run(
        [node, str(script), str(FORGE_JS), json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_settings_tab_renders_safe_provider_configuration_without_secret_field(tmp_path: Path) -> None:
    html = _render(tmp_path, {
        "data": {
            "settings": {
                "local_provider": {
                    "base_url": "http://127.0.0.1:8080/v1",
                    "model_id": "m1",
                    "model_storage_dir": "D:/models",
                },
                "openrouter": {
                    "enabled": False,
                    "api_key_env": "OPENROUTER_API_KEY",
                    "credential_configured": False,
                    "base_url": "https://openrouter.ai/api/v1",
                },
            },
            "openrouterCatalog": {"status": "disabled"},
        }
    })
    assert "data-setting-local-dir" in html
    assert "D:/models" in html
    assert "data-setting-openrouter-env" in html
    assert "OPENROUTER_API_KEY" in html
    assert "data-setting-openrouter-token" not in html
    assert "sk-" not in html.lower()


def test_settings_tab_exposes_runtime_kind_and_lm_studio_support(tmp_path: Path) -> None:
    html = _render(tmp_path, {
        "data": {
            "settings": {
                "local_provider": {
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model_id": "m1",
                    "model_storage_dir": "D:/models",
                    "runtime_kind": "lm_studio",
                },
                "openrouter": {"enabled": False, "api_key_env": "OPENROUTER_API_KEY"},
            },
            "openrouterCatalog": {"status": "disabled"},
        }
    })
    # Runtime selector with both local server kinds, LM Studio preselected from settings.
    assert "data-setting-local-runtime" in html
    assert "llama.cpp" in html
    assert "LM Studio" in html
    assert 'value="lm_studio" selected' in html
    # Base URL quick-fill presets for the two default ports. Host root WITHOUT a trailing /v1 —
    # the local provider appends /v1/chat/completions itself, so a /v1 suffix would double it.
    assert 'data-local-base-preset="http://127.0.0.1:8080"' in html
    assert 'data-local-base-preset="http://127.0.0.1:1234"' in html
    assert "/v1/v1" not in html
    # The deferred-automation caveat must be stated truthfully in the UI.
    assert "後日対応" in html


def test_overview_tab_includes_forge_usage_help(tmp_path: Path) -> None:
    script = tmp_path / "overview.js"
    script.write_text(_NODE_TEMPLATE.replace("_settingsHtml", "_overviewHtml"), encoding="utf-8")
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, str(script), str(FORGE_JS), json.dumps({"data": {"status": {}, "providers": [], "loadouts": []}})],
        capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    assert "Forge の使い方" in proc.stdout
    assert "Benchmark" in proc.stdout and "Arena" in proc.stdout
