"""PFG-23 — Benchmark Preset selector UI render tests.

Drives the real web/js/forge.js benchmark builder under a node DOM stub: the four primary
presets render as checkboxes, depth defaults to standard (deep not forced), and selecting
an external provider raises a policy warning.
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
const F = global.window.Forge;
const input = JSON.parse(process.argv[3]);
Object.assign(F._state.bench, input.bench || {});
process.stdout.write(F._benchmarkHtml(input.data));
"""


def _render(tmp_path, payload: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "bench.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(payload)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


_PRESETS = [
    {"preset_id": "quick", "display_name": "Quick", "recommended_routes": ["micro_patch"]},
    {"preset_id": "web_app", "display_name": "Web App", "recommended_routes": ["patch_dsl"]},
    {"preset_id": "repair", "display_name": "Repair", "recommended_routes": ["repair_loop"]},
    {"preset_id": "greenfield", "display_name": "Greenfield", "recommended_routes": ["greenfield_skeleton"]},
    {"preset_id": "db_persistence", "display_name": "DB", "recommended_routes": ["patch_dsl"]},
]


def test_primary_presets_render_as_checkboxes(tmp_path):
    html = _render(tmp_path, {"data": {"presets": _PRESETS, "providers": []}, "bench": {}})
    for pid in ("quick", "web_app", "repair", "greenfield"):
        assert 'data-bench-preset="' + pid + '"' in html
    # Non-primary preset is tucked under a "More presets" disclosure, not a top checkbox grid.
    assert "More presets" in html


def test_depth_defaults_to_standard_not_deep(tmp_path):
    html = _render(tmp_path, {"data": {"presets": _PRESETS, "providers": []}, "bench": {}})
    # 'standard' is the active segment; 'deep' is present but not active by default.
    assert 'data-bench-depth="standard"' in html
    assert 'forge-seg active" data-bench-depth="standard"' in html
    assert 'forge-seg active" data-bench-depth="deep"' not in html


def test_external_provider_shows_policy_warning(tmp_path):
    data = {
        "presets": _PRESETS,
        "providers": [{"provider_id": "openrouter", "source_class": "external_cloud", "health": "disabled"}],
    }
    html = _render(tmp_path, {"data": data, "bench": {"provider": "openrouter"}})
    assert "forge-warn" in html
    assert "External provider selected" in html


def test_run_disabled_until_preset_provider_model_chosen(tmp_path):
    data = {"presets": _PRESETS, "providers": [{"provider_id": "local_openai_compatible", "source_class": "self_hosted", "health": "ready"}]}
    # Nothing selected -> Run disabled.
    html0 = _render(tmp_path, {"data": data, "bench": {}})
    assert "data-bench-run disabled" in html0
    # Preset + provider + model -> Run enabled.
    html1 = _render(tmp_path, {"data": data, "bench": {"presets": ["quick"], "provider": "local_openai_compatible", "model": "m1"}})
    assert "data-bench-run disabled" not in html1
    assert "data-bench-run" in html1
