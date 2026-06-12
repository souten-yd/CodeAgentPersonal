"""PFG-26 — Loadouts UI and persistence.

Backend: applying a loadout updates the stage policy and records the active loadout; a
risky loadout requires explicit acknowledgement (409). UI: loadout cards render with an
Apply button, the active one is marked, and risky ones carry a warning.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.forge import router as forge_router

ROOT = Path(__file__).resolve().parent.parent
FORGE_JS = ROOT / "web" / "js" / "forge.js"


def _client(tmp_path):
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(forge_router)
    return TestClient(app)


def test_seven_default_loadouts_present(tmp_path):
    loadouts = _client(tmp_path).get("/api/forge/loadouts").json()["loadouts"]
    ids = {l["loadout_id"] for l in loadouts}
    assert {"local_safe", "local_fast", "local_deep", "hybrid_balanced",
            "openrouter_review", "greenfield_builder", "repair_specialist"} <= ids


def test_apply_safe_loadout_updates_stage_policy_and_marks_active(tmp_path):
    c = _client(tmp_path)
    res = c.post("/api/forge/loadouts/local_safe/apply", json={})
    assert res.status_code == 200
    applied = {a["stage"]: a["mode"] for a in res.json()["applied_stages"]}
    assert applied.get("patch_generation") == "shadow_select"
    assert applied.get("final_summary") == "disabled"
    # Stage policy reflects the applied override.
    policy = {e["stage"]: e["mode"] for e in c.get("/api/forge/stage-policy").json()["stage_policy"]}
    assert policy["final_summary"] == "disabled"
    # Active loadout marked + shown in status.
    assert c.get("/api/forge/status").json()["active_loadout"] == "local_safe"
    active = next(l for l in c.get("/api/forge/loadouts").json()["loadouts"] if l["loadout_id"] == "local_safe")
    assert active["active"] is True


def test_risky_loadout_requires_acknowledgement(tmp_path):
    c = _client(tmp_path)
    # OpenRouter Review is risky (external); apply without ack -> 409.
    assert c.post("/api/forge/loadouts/openrouter_review/apply", json={}).status_code == 409
    ok = c.post("/api/forge/loadouts/openrouter_review/apply",
                json={"acknowledge_risky": True})
    assert ok.status_code == 200
    assert c.get("/api/forge/status").json()["active_loadout"] == "openrouter_review"


def test_unknown_loadout_apply_404(tmp_path):
    assert _client(tmp_path).post("/api/forge/loadouts/nope/apply", json={}).status_code == 404


# ---- render ----

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
process.stdout.write(global.window.Forge._loadoutsHtml(JSON.parse(process.argv[3])));
"""


def _render(tmp_path, data: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "lo.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(data)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_loadout_cards_render_active_and_risky(tmp_path):
    data = {"loadouts": [
        {"loadout_id": "local_safe", "display_name": "Local Safe", "description": "safe",
         "source_mode": "local_only", "provider_preferences": ["local_openai_compatible"],
         "risky": False, "active": True},
        {"loadout_id": "openrouter_review", "display_name": "OpenRouter Review", "description": "ext",
         "source_mode": "frontier_preferred", "provider_preferences": ["openrouter"],
         "risky": True, "active": False},
    ]}
    html = _render(tmp_path, data)
    assert "Local Safe" in html and "OpenRouter Review" in html
    # Active loadout marked + its Apply button disabled.
    assert "forge-loadout-active" in html
    assert 'data-loadout="local_safe" data-risky="0" disabled' in html
    # Risky loadout carries a warning pill and a risky-flagged Apply button.
    assert "forge-warn-pill" in html
    assert 'data-loadout="openrouter_review" data-risky="1"' in html
