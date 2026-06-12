"""PFG-36 — controlled Forge primary cutover for a selected stage.

Cutover needs non-regressing shadow evidence + explicit acknowledgement (no automatic
cutover), promotes the stage to Forge primary with legacy fallback, and a tested rollback
reverts the stage to shadow (non-live).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge.forge_service import ForgeService
from agent.model_forge.shadow import compare_stage
from agent.model_forge.schema import ForgeExecutionResult
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.stage_taxonomy import ForgeStage, StageMode
from app.api.forge import router as forge_router


def _client(tmp_path):
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(forge_router)
    return TestClient(app)


def _record_shadow(tmp_path, stage, *, regression=False):
    """Seed a shadow comparison for the stage via the service's shadow store."""
    svc = ForgeService(tmp_path)
    legacy = ForgeExecutionResult(request_id="r", provider_id="legacy", model_id="lm",
                                  route_id=ForgeRoute.DIRECT_PATCH, stage=stage, contract_valid=True)
    forge = ForgeExecutionResult(request_id="r", provider_id="forge", model_id="fm",
                                 route_id=ForgeRoute.DIRECT_PATCH, stage=stage,
                                 contract_valid=not regression, errors=[] if not regression else ["empty_output"])
    cmp = compare_stage(stage, legacy_result=legacy, legacy_output="legacy",
                        forge_result=forge, forge_output="" if regression else "forge")
    svc.shadow.record(cmp)


def test_cutover_requires_shadow_evidence(tmp_path):
    c = _client(tmp_path)
    # No shadow recorded for this stage -> 400.
    resp = c.post("/api/forge/cutover", json={"stage": "failure_classification", "acknowledge": True})
    assert resp.status_code == 400


def test_cutover_requires_acknowledgement(tmp_path):
    _record_shadow(tmp_path, ForgeStage.FAILURE_CLASSIFICATION)
    c = _client(tmp_path)
    # Shadow present but no acknowledgement -> 409 (no automatic cutover).
    assert c.post("/api/forge/cutover", json={"stage": "failure_classification"}).status_code == 409


def test_regression_blocks_cutover(tmp_path):
    _record_shadow(tmp_path, ForgeStage.REPAIR, regression=True)
    c = _client(tmp_path)
    resp = c.post("/api/forge/cutover", json={"stage": "repair", "acknowledge": True})
    assert resp.status_code == 400


def test_cutover_then_rollback(tmp_path):
    _record_shadow(tmp_path, ForgeStage.FAILURE_CLASSIFICATION)
    c = _client(tmp_path)
    # Acknowledged cutover promotes the stage to Forge primary with legacy fallback.
    cut = c.post("/api/forge/cutover", json={"stage": "failure_classification", "acknowledge": True})
    assert cut.status_code == 200
    body = cut.json()
    assert body["forge_primary"] is True and body["legacy_fallback"] is True
    assert body["status"] == "active"
    # Stage matrix now routes live for this stage.
    policy = {e["stage"]: e["mode"] for e in c.get("/api/forge/stage-policy").json()["stage_policy"]}
    assert policy["failure_classification"] == "auto_select"

    # Rollback reverts to shadow (non-live) without an acknowledgement.
    rb = c.post("/api/forge/cutover/failure_classification/rollback")
    assert rb.status_code == 200
    assert rb.json()["status"] == "rolled_back"
    policy2 = {e["stage"]: e["mode"] for e in c.get("/api/forge/stage-policy").json()["stage_policy"]}
    assert policy2["failure_classification"] == "shadow_select"
    # Cutover record listing reflects the rolled-back state.
    cutovers = {x["stage"]: x for x in c.get("/api/forge/cutover").json()["cutovers"]}
    assert cutovers["failure_classification"]["status"] == "rolled_back"
