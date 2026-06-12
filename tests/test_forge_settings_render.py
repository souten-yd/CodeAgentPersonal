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
