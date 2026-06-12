"""PFG-25 — Stage Matrix and Route Matrix UI render tests.

Both matrices are hidden by default behind Advanced disclosures, current stage mode is
shown quickly, and unsafe/live-routing changes carry a warning pill.
"""
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
process.stdout.write(global.window.Forge._advancedHtml(JSON.parse(process.argv[3])));
"""


def _render(tmp_path, data: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "adv.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(data)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


_DATA = {
    "stagePolicy": [
        {"stage": "patch_generation", "mode": "shadow_select", "reason": "taxonomy_default", "fixed_model_id": ""},
        {"stage": "repair", "mode": "auto_select", "reason": "ui_advanced", "fixed_model_id": "big"},
    ],
    "routePolicy": [
        {"change_class": "small", "candidate_routes": ["direct_patch", "patch_dsl"], "critical_gate_required": False},
        {"change_class": "critical", "candidate_routes": ["critical_gate", "blueprint_slice"], "critical_gate_required": True},
    ],
}


def test_matrices_are_collapsible_and_hidden_by_default(tmp_path):
    html = _render(tmp_path, _DATA)
    # Both matrices live inside <details> that are NOT open by default.
    assert html.count("<details") == 2
    assert "open" not in html.split("<summary")[0]
    assert "Stage Matrix" in html and "Route Matrix" in html


def test_stage_mode_shown_and_live_mode_warned(tmp_path):
    html = _render(tmp_path, _DATA)
    assert 'data-stage="patch_generation"' in html
    # auto_select stage carries a live-routing warning pill; shadow_select does not.
    assert "routes live" in html
    assert html.count("forge-warn-pill") >= 1
    # Current mode preselected in the dropdown.
    assert '<option value="auto_select" selected>' in html


def test_route_matrix_marks_critical_gate(tmp_path):
    html = _render(tmp_path, _DATA)
    assert "critical_gate" in html
    assert "critical gate" in html  # warning pill label for critical change class
