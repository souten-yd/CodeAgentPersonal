"""StateMirror for backend/UI/persistence/runtime consistency.

StateMirror compares state observations from different surfaces. Backend state is
treated as authoritative when supplied; UI, persistence, and runtime evidence
must agree with it or produce visible proof requirements.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import TwinControlPlaneModel


class StateSurface(StrEnum):
    BACKEND = "backend"
    UI_PROJECTION = "ui_projection"
    PERSISTENCE = "persistence"
    RUNTIME = "runtime"


class StateObservation(TwinControlPlaneModel):
    path: str = Field(min_length=1)
    value: Any = None
    surface: StateSurface
    evidence_status: str = "observed"  # observed | passed | failed | unavailable
    authoritative: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class StateMirrorFinding(TwinControlPlaneModel):
    finding_id: str = Field(min_length=1)
    severity: str = "advisory"       # hard | soft | advisory
    status: str = "needs_proof"      # passed | needs_proof | blocked | unavailable
    path: str = Field(min_length=1)
    message: str = Field(min_length=1)
    expected: Any = None
    actual: Any = None
    surfaces: list[StateSurface] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)


class StateMirrorReport(TwinControlPlaneModel):
    report_id: str = Field(min_length=1)
    accepted: bool = False
    blocked: bool = False
    findings: list[StateMirrorFinding] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    unavailable_evidence: list[str] = Field(default_factory=list)


_EXECUTE_PATHS = {"can_execute", "controls.can_execute", "workflow_state.can_execute"}
_CONTINUE_PATHS = {"can_continue", "controls.can_continue", "workflow_state.can_continue"}


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _by_path(observations: Iterable[StateObservation]) -> dict[str, StateObservation]:
    return {observation.path: observation for observation in observations}


def _finding(
    *,
    finding_id: str,
    severity: str,
    status: str,
    path: str,
    message: str,
    expected: Any = None,
    actual: Any = None,
    surfaces: Iterable[StateSurface] = (),
    proof_requirements: Iterable[str] = (),
) -> StateMirrorFinding:
    return StateMirrorFinding(
        finding_id=finding_id,
        severity=severity,
        status=status,
        path=path,
        message=message,
        expected=expected,
        actual=actual,
        surfaces=list(surfaces),
        proof_requirements=_unique(proof_requirements),
    )


def _state_path_severity(path: str) -> str:
    lowered = path.lower()
    if path in _EXECUTE_PATHS or path in _CONTINUE_PATHS:
        return "hard"
    if any(token in lowered for token in ("workflow_state", "proposal_status", "portal_run", "capsule", "plan_revision")):
        return "hard"
    if any(token in lowered for token in ("completed_plan_item_count", "artifact", "persisted")):
        return "hard"
    return "soft"


def compare_state_mirror(
    *,
    backend: Iterable[StateObservation] = (),
    ui: Iterable[StateObservation] = (),
    persisted: Iterable[StateObservation] = (),
    runtime: Iterable[StateObservation] = (),
) -> StateMirrorReport:
    """Compare state observations and produce proof requirements."""
    backend_by_path = _by_path(backend)
    ui_by_path = _by_path(ui)
    persisted_by_path = _by_path(persisted)
    runtime_by_path = _by_path(runtime)
    findings: list[StateMirrorFinding] = []

    for path, runtime_obs in sorted(runtime_by_path.items()):
        if runtime_obs.evidence_status == "unavailable":
            findings.append(_finding(
                finding_id=f"state_mirror.runtime_unavailable:{path}",
                severity="advisory",
                status="unavailable",
                path=path,
                message="Runtime evidence is unavailable and must not be treated as pass.",
                actual=runtime_obs.value,
                surfaces=[StateSurface.RUNTIME],
                proof_requirements=[f"Record runtime evidence or unavailable status for {path}."],
            ))

    for path, backend_obs in sorted(backend_by_path.items()):
        ui_obs = ui_by_path.get(path)
        if ui_obs is not None and ui_obs.value != backend_obs.value:
            hard_control = (path in _EXECUTE_PATHS or path in _CONTINUE_PATHS) and backend_obs.value is False and ui_obs.value is True
            severity = "hard" if hard_control else _state_path_severity(path)
            findings.append(_finding(
                finding_id=f"state_mirror.ui_backend_mismatch:{path}",
                severity=severity,
                status="blocked" if severity == "hard" else "needs_proof",
                path=path,
                message="UI projection disagrees with backend-authoritative state.",
                expected=backend_obs.value,
                actual=ui_obs.value,
                surfaces=[StateSurface.BACKEND, StateSurface.UI_PROJECTION],
                proof_requirements=[f"Align UI projection for backend-authoritative state {path}."],
            ))

        persisted_obs = persisted_by_path.get(path)
        if persisted_obs is not None and persisted_obs.value != backend_obs.value:
            reload_regression = "completed_plan_item_count" in path or "plan_revision" in path
            findings.append(_finding(
                finding_id=f"state_mirror.persistence_backend_mismatch:{path}",
                severity="hard" if reload_regression else _state_path_severity(path),
                status="blocked" if reload_regression else "needs_proof",
                path=path,
                message="Persisted state differs from backend-authoritative state.",
                expected=backend_obs.value,
                actual=persisted_obs.value,
                surfaces=[StateSurface.BACKEND, StateSurface.PERSISTENCE],
                proof_requirements=[f"Prove persistence reload preserves authoritative state {path}."],
            ))

    for path, persisted_obs in sorted(persisted_by_path.items()):
        runtime_obs = runtime_by_path.get(path)
        if runtime_obs is None or runtime_obs.evidence_status == "unavailable":
            continue
        if runtime_obs.value != persisted_obs.value:
            findings.append(_finding(
                finding_id=f"state_mirror.persistence_runtime_mismatch:{path}",
                severity=_state_path_severity(path),
                status="blocked" if _state_path_severity(path) == "hard" else "needs_proof",
                path=path,
                message="Persisted artifact state differs from runtime observation.",
                expected=persisted_obs.value,
                actual=runtime_obs.value,
                surfaces=[StateSurface.PERSISTENCE, StateSurface.RUNTIME],
                proof_requirements=[f"Reconcile persisted artifact state with runtime observation for {path}."],
            ))

    proof_requirements = _unique(proof for finding in findings for proof in finding.proof_requirements)
    unavailable = _unique(finding.path for finding in findings if finding.status == "unavailable")
    blocked = any(finding.status == "blocked" for finding in findings)
    accepted = not blocked and not unavailable and not any(finding.status == "needs_proof" for finding in findings)
    return StateMirrorReport(
        report_id="state_mirror:comparison",
        accepted=accepted,
        blocked=blocked,
        findings=findings,
        proof_requirements=proof_requirements,
        unavailable_evidence=unavailable,
    )


__all__ = [
    "StateMirrorFinding",
    "StateMirrorReport",
    "StateObservation",
    "StateSurface",
    "compare_state_mirror",
]
