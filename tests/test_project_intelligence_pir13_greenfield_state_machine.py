from __future__ import annotations

import pytest

from agent.project_intelligence.greenfield_state_machine import (
    GreenfieldOutcome,
    GreenfieldStateMachine,
    GreenfieldStateStore,
)


def test_greenfield_state_machine_persists_and_resumes(tmp_path) -> None:
    store = GreenfieldStateStore(tmp_path)
    machine = GreenfieldStateMachine(store)

    state = machine.start(
        project_id="p1",
        workspace_id="w1",
        project_path=str(tmp_path / "workspace"),
        requirement_revision="req-1",
    )
    state = machine.apply(
        state,
        GreenfieldOutcome(
            target_state="BLUEPRINT_PROPOSED",
            blueprint_revision="bp-1",
            idempotency_key="bp-proposed",
        ),
    )
    state = machine.apply(
        state,
        GreenfieldOutcome(
            target_state="WAITING_BLUEPRINT_DECISION",
            blueprint_revision="bp-1",
            idempotency_key="bp-wait",
        ),
    )

    restored = store.load(state.session_id)
    assert restored.state == "WAITING_BLUEPRINT_DECISION"
    assert restored.requirement_revision == "req-1"
    assert restored.blueprint_revision == "bp-1"
    assert [t.to_state for t in restored.transitions] == [
        "PROJECT_PREPARED",
        "BLUEPRINT_PROPOSED",
        "WAITING_BLUEPRINT_DECISION",
    ]


def test_greenfield_state_machine_accepts_typed_canonical_slice_outcomes(tmp_path) -> None:
    machine = GreenfieldStateMachine(GreenfieldStateStore(tmp_path))
    state = machine.start(project_id="p1", workspace_id="w1", project_path=str(tmp_path / "workspace"))
    for outcome in [
        GreenfieldOutcome(target_state="BLUEPRINT_PROPOSED", blueprint_revision="bp-1", idempotency_key="1"),
        GreenfieldOutcome(target_state="BLUEPRINT_ACTIVE", blueprint_revision="bp-1", idempotency_key="2"),
        GreenfieldOutcome(target_state="PLAN_COMPILED", plan_pool_id="pool-1", idempotency_key="3"),
        GreenfieldOutcome(target_state="SLICE_READY", plan_item_id="item-1", idempotency_key="4"),
        GreenfieldOutcome(target_state="PROPOSAL_READY", proposal_id="proposal-1", idempotency_key="5"),
        GreenfieldOutcome(target_state="APPLY_COMPLETED", apply_ref="apply-1", source_revision="src-1", idempotency_key="6"),
        GreenfieldOutcome(target_state="TWIN_REFRESHED", twin_revision="tw-1", idempotency_key="7"),
        GreenfieldOutcome(target_state="VERIFICATION_COMPLETED", verification_ref="verify-1", status="passed", idempotency_key="8"),
        GreenfieldOutcome(
            target_state="CONVERGENCE_EVALUATED",
            convergence_report_id="conv-1",
            convergence_decision="continue",
            idempotency_key="9",
        ),
        GreenfieldOutcome(target_state="NEXT_SLICE", idempotency_key="10"),
    ]:
        state = machine.apply(state, outcome)

    assert state.state == "NEXT_SLICE"
    assert state.completed_slices == [0]
    assert state.current_slice_index == 1
    assert state.plan_pool_id == "pool-1"
    assert state.verification_ref == "verify-1"
    assert state.convergence_report_id == "conv-1"


def test_greenfield_state_machine_is_idempotent_by_transition_key(tmp_path) -> None:
    machine = GreenfieldStateMachine(GreenfieldStateStore(tmp_path))
    state = machine.start(project_id="p1", workspace_id="w1", project_path=str(tmp_path / "workspace"))
    first_count = len(state.transitions)

    replay = machine.apply(
        state,
        GreenfieldOutcome(target_state="PROJECT_PREPARED", idempotency_key="greenfield:start"),
    )

    assert replay.state == "PROJECT_PREPARED"
    assert len(replay.transitions) == first_count


def test_greenfield_state_machine_rejects_invalid_transitions(tmp_path) -> None:
    machine = GreenfieldStateMachine(GreenfieldStateStore(tmp_path))
    state = machine.start(project_id="p1", workspace_id="w1", project_path=str(tmp_path / "workspace"))

    with pytest.raises(ValueError, match="invalid greenfield transition"):
        machine.apply(state, GreenfieldOutcome(target_state="COMPLETED", idempotency_key="bad-complete"))


def test_greenfield_completion_requires_verification_and_convergence(tmp_path) -> None:
    machine = GreenfieldStateMachine(GreenfieldStateStore(tmp_path))
    state = machine.start(project_id="p1", workspace_id="w1", project_path=str(tmp_path / "workspace"))
    for outcome in [
        GreenfieldOutcome(target_state="BLUEPRINT_PROPOSED", blueprint_revision="bp-1", idempotency_key="1"),
        GreenfieldOutcome(target_state="BLUEPRINT_ACTIVE", blueprint_revision="bp-1", idempotency_key="2"),
        GreenfieldOutcome(target_state="PLAN_COMPILED", plan_pool_id="pool-1", idempotency_key="3"),
        GreenfieldOutcome(target_state="SLICE_READY", plan_item_id="item-1", idempotency_key="4"),
        GreenfieldOutcome(target_state="PROPOSAL_READY", proposal_id="proposal-1", idempotency_key="5"),
        GreenfieldOutcome(target_state="APPLY_COMPLETED", apply_ref="apply-1", idempotency_key="6"),
        GreenfieldOutcome(target_state="TWIN_REFRESHED", twin_revision="tw-1", idempotency_key="7"),
        GreenfieldOutcome(target_state="VERIFICATION_COMPLETED", verification_ref="verify-1", idempotency_key="8"),
        GreenfieldOutcome(target_state="CONVERGENCE_EVALUATED", convergence_report_id="conv-1", idempotency_key="9"),
        GreenfieldOutcome(target_state="COMPLETION_CANDIDATE", idempotency_key="10"),
    ]:
        state = machine.apply(state, outcome)

    blocked = machine.apply(state, GreenfieldOutcome(target_state="COMPLETED", idempotency_key="11"))
    assert blocked.state == "BLOCKED"
    assert "completion requires canonical verification" in blocked.blocked_reasons[-1]
