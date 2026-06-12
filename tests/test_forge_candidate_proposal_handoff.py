from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge.schema import ArenaCandidate, ForgeExecutionResult
from app.api.forge import router as forge_router

ROOT = Path(__file__).resolve().parent.parent
FORGE_JS = ROOT / "web" / "js" / "forge.js"


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(forge_router)
    return TestClient(app)


def _write_arena_candidate(
    tmp_path: Path,
    *,
    candidate_id: str = "cand_arena_pfh8_0",
    contract_valid: bool = True,
    raw_output: str = "def add(a, b):\n    return a + b\n",
    errors: list[str] | None = None,
) -> dict:
    run_dir = tmp_path / "model_forge" / "arena_runs" / "arena_pfh8"
    run_dir.mkdir(parents=True, exist_ok=True)
    result = ForgeExecutionResult(
        request_id="arena_pfh8_c0",
        provider_id="local_openai_compatible",
        model_id="local-model",
        route_id="micro_patch",
        stage="patch_generation",
        contract_valid=contract_valid,
        latency_ms=17,
        errors=list(errors or []),
    )
    (run_dir / f"{candidate_id}.result.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    if raw_output:
        (run_dir / f"{candidate_id}.raw.txt").write_text(raw_output, encoding="utf-8")
    candidate = ArenaCandidate(
        candidate_id=candidate_id,
        arena_run_id="arena_pfh8",
        model_id="local-model",
        provider_id="local_openai_compatible",
        route_id="micro_patch",
        preset_id="quick_standard",
        task_id="task-1",
        execution_result_ref=f"{candidate_id}.result.json",
    )
    record = {
        "schema_version": "forge.v1",
        "arena_run_id": "arena_pfh8",
        "stage": "patch_generation",
        "preset_id": "quick_standard",
        "preset_ids": ["quick_standard"],
        "benchmark_depth": "standard",
        "task_id": "task-1",
        "source_mode": "local_only",
        "privacy_mode": "no_external_code",
        "created_at": "2026-06-12T00:00:00+00:00",
        "candidates": [candidate.model_dump(mode="json")],
    }
    (run_dir / "arena.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def test_eligible_candidate_creates_proposal_draft_only(tmp_path: Path) -> None:
    _write_arena_candidate(tmp_path)
    c = _client(tmp_path)

    resp = c.post("/api/forge/arena/candidates/cand_arena_pfh8_0/proposal-draft")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    draft = body["proposal_draft"]
    assert draft["candidate_id"] == "cand_arena_pfh8_0"
    assert draft["arena_run_id"] == "arena_pfh8"
    assert draft["provider_id"] == "local_openai_compatible"
    assert draft["model_id"] == "local-model"
    assert draft["route_id"] == "micro_patch"
    assert draft["preset_id"] == "quick_standard"
    assert draft["risk_level"] == "low"
    assert draft["source_mode"] == "local_only"
    assert draft["privacy_mode"] == "no_external_code"
    assert draft["evaluator_score"]["verdict"] == "eligible"
    assert draft["metadata"]["safe_apply_run"] is False
    assert draft["metadata"]["verification_run"] is False
    assert draft["metadata"]["source_mutation"] is False
    assert "Run changes only through Atlas Safe Apply." in draft["required_safe_apply_steps"]
    assert "focused_tests" in draft["required_verification_steps"]
    assert Path(draft["artifact_ref"]).exists()
    assert not (tmp_path / "atlas" / "safe_apply").exists()
    assert not (tmp_path / "atlas" / "verification").exists()

    record = c.get("/api/forge/arena/runs/arena_pfh8").json()
    cand = record["candidates"][0]
    assert cand["adoption_state"] == "proposal_created"
    assert cand["eligible_for_proposal"] is True
    assert cand["proposal_draft"]["status"] == "proposal_draft"


def test_ineligible_candidate_is_blocked_with_evaluator_reasons(tmp_path: Path) -> None:
    _write_arena_candidate(
        tmp_path,
        contract_valid=False,
        raw_output="",
        errors=["policy_blocked:local_only_blocks_external"],
    )
    c = _client(tmp_path)

    resp = c.post("/api/forge/arena/candidates/cand_arena_pfh8_0/proposal-draft")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["proposal_draft"] is None
    assert body["blocked_reasons"]
    assert "contract_parse" in body["blocked_reasons"][0]
    assert not (tmp_path / "model_forge" / "proposal_drafts").exists()
    record = c.get("/api/forge/arena/runs/arena_pfh8").json()
    cand = record["candidates"][0]
    assert cand["adoption_state"] == "rejected"
    assert cand["eligible_for_proposal"] is False


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
process.stdout.write(F._arenaHtml(JSON.parse(process.argv[3])));
"""


def _render_arena(tmp_path: Path, data: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "arena.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run(
        [node, str(script), str(FORGE_JS), json.dumps(data)],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_arena_ui_labels_proposal_draft_and_disables_blocked_candidate(tmp_path: Path) -> None:
    html = _render_arena(tmp_path, {
        "arena": {
            "arena_run_id": "arena_pfh8",
            "candidates": [
                {
                    "candidate_id": "cand_ok",
                    "model_id": "m-ok",
                    "route_id": "micro_patch",
                    "adoption_state": "not_applied",
                    "risk_level": "low",
                    "result": {"contract_valid": True, "latency_ms": 1},
                    "evaluator_score": {"final_score": 1.0, "verdict": "eligible"},
                    "blocked_reasons": [],
                    "eligible_for_proposal": True,
                    "proposal_draft": {"status": "not_created"},
                },
                {
                    "candidate_id": "cand_blocked",
                    "model_id": "m-blocked",
                    "route_id": "direct_patch",
                    "adoption_state": "rejected",
                    "risk_level": "medium",
                    "result": {"contract_valid": False, "latency_ms": 0},
                    "evaluator_score": {"final_score": 0.0, "verdict": "rejected"},
                    "blocked_reasons": ["contract_parse:policy_blocked"],
                    "eligible_for_proposal": False,
                    "proposal_draft": {"status": "not_created"},
                },
            ],
        },
    })
    assert "Create Proposal draft" in html
    assert "approval required" in html
    assert "Blocked: contract_parse:policy_blocked" in html
    assert 'data-candidate-proposal="cand_blocked" disabled' in html
    assert "Adopt → requires Safe Apply" not in html
