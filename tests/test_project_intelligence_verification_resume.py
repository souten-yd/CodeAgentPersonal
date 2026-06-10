"""PI-19 verification, checkpoint, and resume integration tests.

Acceptance criteria (implementation plan PI-19):
- verification automatically ingests runtime observations;
- post-verification Convergence runs;
- restart resumes from exact revisions;
- external source changes are detected before continuation;
- no duplicate apply or verification on replay;
- rollback remains available.
"""

from __future__ import annotations

from agent.project_intelligence.adapters.atlas_verification import AtlasVerificationBridge
from agent.project_intelligence.checkpoint import (
    REFRESH_NEEDED,
    RESUME,
    Checkpoint,
    CheckpointController,
)
from agent.project_intelligence.contracts import RuntimeObservationRecord


def _checkpoint(**over):
    base = dict(project_id="p1", workspace_id="w1", plan_pool_id="pp", plan_item_id="pi",
                requirement_revision="req1", blueprint_revision="bp1", actual_twin_revision="tw1",
                convergence_report_id="cv1", plan_pool_revision="pr1", rollout_mode="active",
                working_tree_hash="hash-A")
    base.update(over)
    return Checkpoint(**base)


def _obs(result, oid):
    return RuntimeObservationRecord(observation_id=oid, project_id="p1", workspace_id="w1",
                                    result=result, summary=result)


# --- Verification ingests observations + requests convergence ----------------

def test_verification_ingests_and_requests_convergence() -> None:
    bridge = AtlasVerificationBridge()
    out = bridge.record_verification(checkpoint=_checkpoint(),
                                     observations=[_obs("passed", "o1"), _obs("passed", "o2")],
                                     idempotency_key="run-1")
    assert out.rollup.passed == 2 and out.rollup.success is True
    assert out.convergence_requested is True
    assert out.last_successful_evidence == ["o1", "o2"]
    assert out.rollback_base_revision == "tw1"  # rollback remains available


def test_unavailable_rollup_blocks_success() -> None:
    bridge = AtlasVerificationBridge()
    out = bridge.record_verification(checkpoint=_checkpoint(),
                                     observations=[_obs("passed", "o1"), _obs("unavailable", "o2")],
                                     idempotency_key="run-x")
    assert out.rollup.success is False  # unavailable never success


# --- No duplicate apply/verification on replay -------------------------------

def test_replay_is_idempotent_no_duplicate() -> None:
    ctrl = CheckpointController()
    bridge = AtlasVerificationBridge(ctrl)
    first = bridge.record_verification(checkpoint=_checkpoint(), observations=[_obs("passed", "o1")],
                                       idempotency_key="run-1")
    replay = bridge.record_verification(checkpoint=_checkpoint(), observations=[_obs("passed", "o1")],
                                        idempotency_key="run-1")
    assert first.checkpoint_id == replay.checkpoint_id
    assert first.duplicate is False and replay.duplicate is True
    assert replay.convergence_requested is False  # not re-run on replay


# --- Restart resumes from exact revisions ------------------------------------

def test_restart_resumes_from_exact_revisions() -> None:
    ctrl = CheckpointController()
    bridge = AtlasVerificationBridge(ctrl)
    bridge.record_verification(checkpoint=_checkpoint(), observations=[_obs("passed", "o1")],
                               idempotency_key="run-1")
    # Simulate restart: a brand-new bridge over the same store.
    bridge2 = AtlasVerificationBridge(ctrl)
    decision = bridge2.resume(project_id="p1", workspace_id="w1", plan_pool_id="pp", plan_item_id="pi",
                              current_actual_revision="tw1", current_working_tree_hash="hash-A")
    assert decision is not None and decision.action == RESUME
    assert decision.from_revisions["blueprint_revision"] == "bp1"
    assert decision.from_revisions["actual_twin_revision"] == "tw1"
    assert decision.rollback_base_revision == "tw1"


# --- External source change detected before continuation ---------------------

def test_external_source_change_detected() -> None:
    ctrl = CheckpointController()
    bridge = AtlasVerificationBridge(ctrl)
    bridge.record_verification(checkpoint=_checkpoint(), observations=[_obs("passed", "o1")],
                               idempotency_key="run-1")
    # The working tree changed (different hash) since the checkpoint.
    decision = bridge.resume(project_id="p1", workspace_id="w1", plan_pool_id="pp", plan_item_id="pi",
                             current_actual_revision="tw1", current_working_tree_hash="hash-B")
    assert decision.action == REFRESH_NEEDED
    assert any("external source change" in r for r in decision.reasons)


def test_revision_change_detected() -> None:
    ctrl = CheckpointController()
    bridge = AtlasVerificationBridge(ctrl)
    bridge.record_verification(checkpoint=_checkpoint(), observations=[_obs("passed", "o1")],
                               idempotency_key="run-1")
    decision = bridge.resume(project_id="p1", workspace_id="w1", plan_pool_id="pp", plan_item_id="pi",
                             current_actual_revision="tw2", current_working_tree_hash="hash-A")
    assert decision.action == REFRESH_NEEDED


# --- Project isolation of checkpoints ----------------------------------------

def test_checkpoint_project_isolation() -> None:
    ctrl = CheckpointController()
    bridge = AtlasVerificationBridge(ctrl)
    bridge.record_verification(checkpoint=_checkpoint(), observations=[_obs("passed", "o1")],
                               idempotency_key="run-1")
    # A different project has no checkpoint for the same plan item.
    assert bridge.resume(project_id="p2", workspace_id="w1", plan_pool_id="pp", plan_item_id="pi",
                         current_actual_revision="tw1", current_working_tree_hash="hash-A") is None
