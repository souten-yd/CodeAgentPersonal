"""PFG-24 — Arena UI: backend enrichment + render.

Backend: get_arena_run enriches candidates with per-candidate result metadata. UI:
arenaHtml renders candidate rows (contract/latency), marks a winner, and shows an
adoption control that requires Safe Apply with no direct apply button.
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


def test_get_arena_run_enriches_candidates_with_result_metadata(tmp_path):
    c = _client(tmp_path)
    run = c.post("/api/forge/arena/run", json={
        "stage": "patch_generation",
        "specs": [{"provider_id": "legacy_atlas", "model_id": "m1", "route_id": "direct_patch"}],
        "source_mode": "local_only",
    }).json()
    got = c.get(f"/api/forge/arena/runs/{run['arena_run_id']}").json()
    cand = got["candidates"][0]
    # Candidate is enriched with persisted result metadata, and never applied.
    assert "result" in cand
    assert set(["contract_valid", "latency_ms", "errors"]).issubset(cand["result"].keys())
    assert cand["adoption_state"] == "not_applied"


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
process.stdout.write(global.window.Forge._arenaHtml(JSON.parse(process.argv[3])));
"""


def _render(tmp_path, data: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "arena.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(data)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_arena_empty_state(tmp_path):
    html = _render(tmp_path, {"arena": None})
    assert "No Arena run yet" in html
    assert "never applied automatically" in html


def test_arena_renders_candidates_winner_and_safe_apply_only(tmp_path):
    record = {
        "arena_run_id": "arena_abc",
        "candidates": [
            {"candidate_id": "c0", "model_id": "fast", "provider_id": "local", "route_id": "direct_patch",
             "adoption_state": "not_applied", "result": {"contract_valid": True, "latency_ms": 120, "errors": []}},
            {"candidate_id": "c1", "model_id": "slow", "provider_id": "local", "route_id": "patch_dsl",
             "adoption_state": "not_applied", "result": {"contract_valid": True, "latency_ms": 900, "errors": []}},
            {"candidate_id": "c2", "model_id": "broken", "provider_id": "local", "route_id": "micro_patch",
             "adoption_state": "not_applied", "result": {"contract_valid": False, "latency_ms": 50, "errors": ["x"]}},
        ],
    }
    html = _render(tmp_path, {"arena": record})
    assert "fast" in html and "slow" in html and "broken" in html
    assert "contract ok" in html and "contract fail" in html
    assert "lat 120 ms" in html
    # Winner is the valid candidate with lowest latency (fast=120), not the broken 50ms one.
    assert "★ winner" in html
    assert html.count("is-winner") == 1
    # Adoption control requires Safe Apply and there is no enabled direct-apply button.
    assert "requires Safe Apply" in html
    assert "Proposal → Safe Apply → Verification" in html
    assert "forge-adopt-btn" in html and "disabled" in html
