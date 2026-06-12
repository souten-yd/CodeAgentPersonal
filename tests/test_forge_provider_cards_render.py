"""PFH-3 provider readiness UI render tests."""
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
process.stdout.write(F._overviewHtml(input.data));
"""


def _render(tmp_path: Path, payload: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "providers.js"
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


def test_provider_card_distinguishes_configured_from_runtime_ready(tmp_path: Path) -> None:
    html = _render(tmp_path, {
        "data": {
            "status": {"forge_enabled": False, "source_mode": "local_only"},
            "providers": [{
                "provider_id": "local_openai_compatible",
                "source_class": "self_hosted",
                "health": "unavailable",
                "health_detail": "runtime_not_probed",
                "configured_state": "configured",
                "runtime_health": "not_probed",
            }],
            "loadouts": [],
        }
    })
    assert "Configured: configured" in html
    assert "Runtime: not_probed" in html
    assert "data-provider-probe=\"local_openai_compatible\"" in html
    assert "Configured, not runtime-ready" in html
