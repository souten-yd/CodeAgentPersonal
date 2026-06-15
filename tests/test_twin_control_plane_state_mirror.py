from __future__ import annotations

from agent.twin_control_plane.state_mirror import StateObservation, StateSurface, compare_state_mirror


def _obs(path: str, value, surface: StateSurface, *, status: str = "observed") -> StateObservation:
    return StateObservation(path=path, value=value, surface=surface, evidence_status=status)


def test_backend_cannot_execute_but_ui_exposes_execute_is_flagged() -> None:
    report = compare_state_mirror(
        backend=[_obs("can_execute", False, StateSurface.BACKEND)],
        ui=[_obs("can_execute", True, StateSurface.UI_PROJECTION)],
    )

    assert report.blocked is True
    assert report.accepted is False
    finding = report.findings[0]
    assert finding.finding_id == "state_mirror.ui_backend_mismatch:can_execute"
    assert finding.severity == "hard"
    assert finding.status == "blocked"
    assert finding.expected is False
    assert finding.actual is True
    assert "Align UI projection for backend-authoritative state can_execute." in report.proof_requirements


def test_reload_loses_completed_plan_item_count_is_flagged() -> None:
    report = compare_state_mirror(
        backend=[_obs("workflow_state.completed_plan_item_count", 3, StateSurface.BACKEND)],
        persisted=[_obs("workflow_state.completed_plan_item_count", 1, StateSurface.PERSISTENCE)],
    )

    assert report.blocked is True
    finding = report.findings[0]
    assert finding.finding_id == "state_mirror.persistence_backend_mismatch:workflow_state.completed_plan_item_count"
    assert finding.status == "blocked"
    assert finding.expected == 3
    assert finding.actual == 1
    assert "Prove persistence reload preserves authoritative state workflow_state.completed_plan_item_count." in report.proof_requirements


def test_persisted_artifact_state_differs_from_runtime_state_is_flagged() -> None:
    report = compare_state_mirror(
        persisted=[_obs("portal_run.capsule_state", "saved", StateSurface.PERSISTENCE)],
        runtime=[_obs("portal_run.capsule_state", "discarded", StateSurface.RUNTIME, status="observed")],
    )

    assert report.blocked is True
    finding = report.findings[0]
    assert finding.finding_id == "state_mirror.persistence_runtime_mismatch:portal_run.capsule_state"
    assert finding.severity == "hard"
    assert finding.expected == "saved"
    assert finding.actual == "discarded"


def test_unavailable_runtime_evidence_is_not_treated_as_pass() -> None:
    report = compare_state_mirror(
        runtime=[_obs("portal_run.state", "unknown", StateSurface.RUNTIME, status="unavailable")],
    )

    assert report.accepted is False
    assert report.blocked is False
    assert report.unavailable_evidence == ["portal_run.state"]
    finding = report.findings[0]
    assert finding.status == "unavailable"
    assert "must not be treated as pass" in finding.message


def test_matching_backend_ui_persistence_runtime_state_accepts() -> None:
    report = compare_state_mirror(
        backend=[
            _obs("workflow_state", "approved_not_started", StateSurface.BACKEND),
            _obs("proposal_status", "proposal_draft", StateSurface.BACKEND),
        ],
        ui=[
            _obs("workflow_state", "approved_not_started", StateSurface.UI_PROJECTION),
            _obs("proposal_status", "proposal_draft", StateSurface.UI_PROJECTION),
        ],
        persisted=[
            _obs("workflow_state", "approved_not_started", StateSurface.PERSISTENCE),
            _obs("proposal_status", "proposal_draft", StateSurface.PERSISTENCE),
        ],
        runtime=[
            _obs("workflow_state", "approved_not_started", StateSurface.RUNTIME, status="observed"),
            _obs("proposal_status", "proposal_draft", StateSurface.RUNTIME, status="observed"),
        ],
    )

    assert report.accepted is True
    assert report.blocked is False
    assert report.findings == []
