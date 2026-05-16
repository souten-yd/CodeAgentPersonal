from pathlib import Path

import pytest

from agent.atlas_approval_gate import AtlasApprovalGate
from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_GATE_PATH = ROOT / "agent" / "atlas_approval_gate.py"


def make_policy_evaluation() -> AtlasPolicyEvaluation:
    return AtlasPolicyEvaluation(
        evaluation_id="eval_1",
        scope="item",
        decision="require_approval",
        pool_id="pool_1",
        item_id="item_1",
        risk_level="high",
        reasons=["high risk item requires approval"],
        categories=["high_risk"],
        requires_user_confirmation=True,
        auto_execution_allowed=False,
    )


def request_item(gate: AtlasApprovalGate, item_id: str = "item_1"):
    return gate.request_approval(scope="item", pool_id="pool_1", item_id=item_id)


def test_request_pool_approval_requires_pool_id() -> None:
    gate = AtlasApprovalGate()

    with pytest.raises(ValueError):
        gate.request_approval(scope="pool", pool_id="")


def test_request_item_approval_requires_pool_and_item_id() -> None:
    gate = AtlasApprovalGate()

    with pytest.raises(ValueError):
        gate.request_approval(scope="item", pool_id="pool_1", item_id="")


def test_request_patch_approval_requires_patch_id() -> None:
    gate = AtlasApprovalGate()

    with pytest.raises(ValueError):
        gate.request_approval(scope="patch", pool_id="pool_1", item_id="item_1", patch_id="")


def test_request_approval_records_policy_evaluation() -> None:
    gate = AtlasApprovalGate()
    evaluation = make_policy_evaluation()

    record = gate.request_approval(
        scope="item",
        pool_id="pool_1",
        item_id="item_1",
        policy_evaluation=evaluation,
    )

    assert record.policy_decision == "require_approval"
    assert record.policy_reasons == ["high risk item requires approval"]
    assert record.policy_categories == ["high_risk"]
    assert record.reason == "high risk item requires approval"
    assert record.metadata["policy_evaluation"]["evaluation_id"] == "eval_1"


def test_approve_record() -> None:
    gate = AtlasApprovalGate()
    record = request_item(gate)

    approved = gate.approve(record.approval_id, decided_by="reviewer", reason="ok")

    assert approved.status == "approved"
    assert approved.decided_by == "reviewer"
    assert approved.decided_at
    assert approved.reason == "ok"
    assert gate.is_item_approved("pool_1", "item_1") is True


def test_reject_record() -> None:
    gate = AtlasApprovalGate()
    record = request_item(gate)

    rejected = gate.reject(record.approval_id, reason="no")

    assert rejected.status == "rejected"
    assert gate.is_item_approved("pool_1", "item_1") is False


def test_revoke_record() -> None:
    gate = AtlasApprovalGate()
    record = request_item(gate)

    revoked = gate.revoke(record.approval_id, reason="changed mind")

    assert revoked.status == "revoked"
    assert gate.is_item_approved("pool_1", "item_1") is False


def test_missing_approval_id_raises_key_error() -> None:
    gate = AtlasApprovalGate()

    with pytest.raises(KeyError):
        gate.approve("missing")


def test_find_records_filters_by_scope_pool_item_status() -> None:
    gate = AtlasApprovalGate()
    first = request_item(gate, "item_1")
    second = request_item(gate, "item_2")
    gate.request_approval(scope="pool", pool_id="pool_1")
    gate.approve(first.approval_id)
    gate.reject(second.approval_id)

    records = gate.find_records(scope="item", pool_id="pool_1", item_id="item_1", status="approved")

    assert records == [first]


def test_snapshot_summarizes_records() -> None:
    gate = AtlasApprovalGate()
    pool_record = gate.request_approval(scope="pool", pool_id="pool_1")
    approved_item = request_item(gate, "item_approved")
    pending_item = request_item(gate, "item_pending")
    rejected_item = request_item(gate, "item_rejected")
    patch_record = gate.request_approval(
        scope="patch",
        pool_id="pool_1",
        item_id="item_approved",
        patch_id="patch_1",
    )
    revoked_item = request_item(gate, "item_revoked")
    gate.approve(pool_record.approval_id)
    gate.approve(approved_item.approval_id)
    gate.reject(rejected_item.approval_id)
    gate.approve(patch_record.approval_id)
    gate.revoke(revoked_item.approval_id)

    snapshot = gate.snapshot("pool_1")

    assert snapshot.approved_pool is True
    assert snapshot.approved_item_ids == ["item_approved"]
    assert snapshot.approved_patch_ids == ["patch_1"]
    assert snapshot.pending_item_ids == ["item_pending"]
    assert snapshot.rejected_item_ids == ["item_rejected"]
    assert snapshot.metadata == {
        "total_records": 6,
        "pending_count": 1,
        "approved_count": 3,
        "rejected_count": 1,
        "revoked_count": 1,
    }


def test_approval_gate_has_no_runtime_api_storage_side_effect_tokens() -> None:
    text = APPROVAL_GATE_PATH.read_text(encoding="utf-8")

    for token in (
        "FastAPI",
        "@app.",
        "subprocess",
        "ImplementationExecutor(",
        "safe_apply",
        "delete_file",
        "AtlasPlanPoolStorage(",
        ".write_text(",
        ".unlink(",
        "run_command(",
    ):
        assert token not in text
