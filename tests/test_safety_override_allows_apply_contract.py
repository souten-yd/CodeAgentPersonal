"""Contract: a human safety override granted after a clarification safety block lets the apply-time
gate proceed (codegen dispatches), while the absence of an override keeps it blocked. Critical
events (critical risk / forbidden action / unsafe or protected path) are never overridable.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_automation_gate_service import AtlasAutomationGateService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _pool(*, status="blocked_safety_review", risk_level="medium", metadata=None) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_ovr",
        root_goal="Goal",
        status=status,
        project_path="/tmp/ws",
        items=[
            AtlasPlanItem(
                item_id="i1", pool_id="pool_ovr", title="Item", goal="Do",
                item_type="implementation", status="approval_required", risk_level=risk_level,
                target_files=["src/i1.py"], metadata={"action_type": "create"},
            )
        ],
        metadata=metadata or {},
    )


def _decide(pool: AtlasPlanPool):
    preset = atlas_auto_policy_presets()["guarded_low_risk"]
    return AtlasAutomationGateService().decide_pre_safe_apply(pool, pool.items[0], preset)


def test_gate_blocks_non_critical_item_without_override():
    decision = _decide(_pool(metadata={}))
    assert decision.decision == "block"
    assert "risk_not_allowed" in decision.reasons


def test_gate_allows_non_critical_block_when_override_granted():
    pool = _pool(metadata={"safety_override_granted_after_clarification": True})
    decision = _decide(pool)
    assert decision.decision == "allow"
    assert "safety_override_granted_after_clarification" in decision.warnings
    assert decision.metadata["safety_override_applied"] is True
    assert "risk_not_allowed" in decision.metadata["safety_override_overridden_reasons"]


def test_override_never_relaxes_critical_event():
    # critical risk -> critical event -> must stay blocked/require_manual even with the override flag.
    pool = _pool(risk_level="critical", metadata={"safety_override_granted_after_clarification": True})
    decision = _decide(pool)
    assert decision.decision != "allow"
    assert "critical_event" in decision.metadata


def _client(tmp_path: Path, pool: AtlasPlanPool) -> TestClient:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    AtlasPlanPoolStorage(Path(tmp_path)).save_pool(pool)
    return TestClient(app)


def test_override_endpoint_requires_blocked_safety_review(tmp_path: Path):
    client = _client(tmp_path, _pool(status="ready"))
    r = client.post("/api/atlas/plan-pools/pool_ovr/safety-override", json={"reason": "reviewed"})
    assert r.status_code == 400, r.text


def test_override_endpoint_grants_and_is_idempotent(tmp_path: Path):
    client = _client(tmp_path, _pool(status="blocked_safety_review", metadata={
        "safety_gate_block_reason_after_clarification": "risk_not_allowed, target_files_too_many",
    }))
    r = client.post("/api/atlas/plan-pools/pool_ovr/safety-override", json={"reason": "reviewed", "approver": "alice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["safety_override_granted_after_clarification"] is True
    assert body["safety_override_after_clarification"]["approver"] == "alice"
    assert body["block_reason"] == "risk_not_allowed, target_files_too_many"

    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_ovr")
    assert reloaded.status == "ready"
    assert reloaded.metadata["safety_override_granted_after_clarification"] is True
    # The apply-time gate now honors the recorded override.
    assert _decide(reloaded).decision == "allow"

    # Idempotent: a second call (already granted, now "ready") still succeeds.
    r2 = client.post("/api/atlas/plan-pools/pool_ovr/safety-override", json={})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "ready"
