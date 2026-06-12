"""PFG-22 — Skill Radar and Leaderboard UI render tests.

Drives the real web/js/forge.js skills builder under a node DOM stub: empty profiles
show a useful empty state; populated profiles render champion cards + per-model score
bars compactly.
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
const data = JSON.parse(process.argv[3]);
process.stdout.write(global.window.Forge._skillsHtml(data));
"""


def _render(tmp_path, data: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "skills.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(data)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_empty_profiles_show_useful_empty_state(tmp_path):
    html = _render(tmp_path, {"leaderboard": [], "profiles": []})
    assert "Skill Radar" in html
    assert "No model profiles yet" in html


def test_champions_and_models_render(tmp_path):
    data = {
        "leaderboard": [
            {"dimension": "patch_generation", "provider_id": "local", "model_id": "big", "score": 0.9},
            {"dimension": "repair", "provider_id": "local", "model_id": "small", "score": 0.4},
        ],
        "profiles": [
            {"provider_id": "local", "model_id": "big",
             "dimension_scores": {"overall": 0.8, "patch_generation": 0.9}, "sample_count": 3},
        ],
    }
    html = _render(tmp_path, data)
    assert "Champions" in html
    assert "patch_generation" in html and "repair" in html
    assert "big" in html
    # Score bars render with a width and a numeric value (compact mobile-friendly).
    assert "forge-bar-fill" in html and "width:90%" in html
    # Model row is clickable (carries a data-model key for the detail drawer).
    assert 'data-model="local/big"' in html
