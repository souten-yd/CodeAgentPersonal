from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


GREENFIELD_STATES: tuple[str, ...] = (
    "NEW",
    "PROJECT_PREPARED",
    "BLUEPRINT_PROPOSED",
    "WAITING_BLUEPRINT_DECISION",
    "BLUEPRINT_ACTIVE",
    "PLAN_COMPILED",
    "SLICE_READY",
    "PROPOSAL_READY",
    "APPLY_COMPLETED",
    "TWIN_REFRESHED",
    "VERIFICATION_COMPLETED",
    "CONVERGENCE_EVALUATED",
    "REPAIR_REQUIRED",
    "REPLAN_REQUIRED",
    "NEXT_SLICE",
    "COMPLETION_CANDIDATE",
    "COMPLETED",
    "BLOCKED",
    "FAILED_RETRYABLE",
)

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"PROJECT_PREPARED", "BLOCKED"},
    "PROJECT_PREPARED": {"BLUEPRINT_PROPOSED", "BLOCKED"},
    "BLUEPRINT_PROPOSED": {"WAITING_BLUEPRINT_DECISION", "BLUEPRINT_ACTIVE", "BLOCKED"},
    "WAITING_BLUEPRINT_DECISION": {"BLUEPRINT_ACTIVE", "BLOCKED"},
    "BLUEPRINT_ACTIVE": {"PLAN_COMPILED", "BLOCKED"},
    "PLAN_COMPILED": {"SLICE_READY", "BLOCKED"},
    "SLICE_READY": {"PROPOSAL_READY", "REPLAN_REQUIRED", "BLOCKED"},
    "PROPOSAL_READY": {"APPLY_COMPLETED", "FAILED_RETRYABLE", "BLOCKED"},
    "APPLY_COMPLETED": {"TWIN_REFRESHED", "FAILED_RETRYABLE", "BLOCKED"},
    "TWIN_REFRESHED": {"VERIFICATION_COMPLETED", "FAILED_RETRYABLE", "BLOCKED"},
    "VERIFICATION_COMPLETED": {"CONVERGENCE_EVALUATED", "REPAIR_REQUIRED", "FAILED_RETRYABLE", "BLOCKED"},
    "CONVERGENCE_EVALUATED": {"NEXT_SLICE", "COMPLETION_CANDIDATE", "REPAIR_REQUIRED", "REPLAN_REQUIRED", "BLOCKED"},
    "REPAIR_REQUIRED": {"PROPOSAL_READY", "FAILED_RETRYABLE", "BLOCKED"},
    "REPLAN_REQUIRED": {"PLAN_COMPILED", "BLOCKED"},
    "NEXT_SLICE": {"SLICE_READY", "COMPLETION_CANDIDATE", "BLOCKED"},
    "COMPLETION_CANDIDATE": {"COMPLETED", "REPAIR_REQUIRED", "REPLAN_REQUIRED", "BLOCKED"},
    "FAILED_RETRYABLE": {"PROPOSAL_READY", "REPAIR_REQUIRED", "BLOCKED"},
    "COMPLETED": set(),
    "BLOCKED": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class GreenfieldOutcome:
    """Typed canonical outcome accepted by the Greenfield state machine."""

    target_state: str
    status: str = "passed"
    idempotency_key: str = ""
    requirement_revision: str | None = None
    blueprint_revision: str | None = None
    twin_revision: str | None = None
    source_revision: str | None = None
    plan_pool_id: str | None = None
    plan_item_id: str | None = None
    proposal_id: str | None = None
    apply_ref: str | None = None
    verification_ref: str | None = None
    convergence_report_id: str | None = None
    convergence_decision: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class GreenfieldTransition:
    from_state: str
    to_state: str
    status: str
    idempotency_key: str
    recorded_at: str
    refs: dict[str, str | None] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class GreenfieldRunState:
    session_id: str
    project_id: str
    workspace_id: str
    project_path: str
    state: str = "NEW"
    current_slice_index: int = 0
    completed_slices: list[int] = field(default_factory=list)
    requirement_revision: str | None = None
    blueprint_revision: str | None = None
    twin_revision: str | None = None
    source_revision: str | None = None
    plan_pool_id: str | None = None
    plan_item_id: str | None = None
    proposal_id: str | None = None
    apply_ref: str | None = None
    verification_ref: str | None = None
    convergence_report_id: str | None = None
    convergence_decision: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)
    transitions: list[GreenfieldTransition] = field(default_factory=list)


class GreenfieldStateStore:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.sessions_dir = self.root_dir / "project_intelligence" / "greenfield_sessions"

    def path(self, session_id: str) -> Path:
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("invalid greenfield session id")
        return self.sessions_dir / f"{session_id}.json"

    def save(self, state: GreenfieldRunState) -> Path:
        path = self.path(state.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_dump_state(state), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> GreenfieldRunState:
        payload = json.loads(self.path(session_id).read_text(encoding="utf-8"))
        transitions = [GreenfieldTransition(**item) for item in payload.pop("transitions", [])]
        return GreenfieldRunState(**payload, transitions=transitions)


class GreenfieldStateMachine:
    def __init__(self, store: GreenfieldStateStore):
        self.store = store

    def start(
        self,
        *,
        project_id: str,
        workspace_id: str,
        project_path: str,
        session_id: str | None = None,
        requirement_revision: str | None = None,
        idempotency_key: str = "greenfield:start",
    ) -> GreenfieldRunState:
        state = GreenfieldRunState(
            session_id=session_id or f"greenfield_{uuid4().hex[:12]}",
            project_id=project_id,
            workspace_id=workspace_id,
            project_path=project_path,
            requirement_revision=requirement_revision,
        )
        state = self.apply(state, GreenfieldOutcome(target_state="PROJECT_PREPARED", status="passed", idempotency_key=idempotency_key))
        self.store.save(state)
        return state

    def apply(self, state: GreenfieldRunState, outcome: GreenfieldOutcome) -> GreenfieldRunState:
        if outcome.target_state not in GREENFIELD_STATES:
            raise ValueError(f"unknown greenfield state: {outcome.target_state}")
        key = outcome.idempotency_key or f"{state.session_id}:{state.state}:{outcome.target_state}"
        for transition in state.transitions:
            if transition.idempotency_key == key:
                return state
        allowed = _ALLOWED_TRANSITIONS.get(state.state, set())
        if outcome.target_state not in allowed:
            raise ValueError(f"invalid greenfield transition: {state.state} -> {outcome.target_state}")
        if outcome.target_state == "COMPLETED" and not self._completion_gate_passed(state, outcome):
            outcome = GreenfieldOutcome(
                target_state="BLOCKED",
                status="blocked",
                idempotency_key=key,
                diagnostics=["completion requires canonical verification and convergence acceptance"],
            )
        refs = {
            "requirement_revision": outcome.requirement_revision,
            "blueprint_revision": outcome.blueprint_revision,
            "twin_revision": outcome.twin_revision,
            "source_revision": outcome.source_revision,
            "plan_pool_id": outcome.plan_pool_id,
            "plan_item_id": outcome.plan_item_id,
            "proposal_id": outcome.proposal_id,
            "apply_ref": outcome.apply_ref,
            "verification_ref": outcome.verification_ref,
            "convergence_report_id": outcome.convergence_report_id,
            "convergence_decision": outcome.convergence_decision,
        }
        transition = GreenfieldTransition(
            from_state=state.state,
            to_state=outcome.target_state,
            status=outcome.status,
            idempotency_key=key,
            recorded_at=_now(),
            refs={k: v for k, v in refs.items() if v},
            evidence_refs=list(outcome.evidence_refs),
            diagnostics=list(outcome.diagnostics),
        )
        state.transitions.append(transition)
        state.state = outcome.target_state
        for field_name, value in refs.items():
            if value:
                setattr(state, field_name, value)
        if outcome.target_state == "NEXT_SLICE":
            if state.current_slice_index not in state.completed_slices:
                state.completed_slices.append(state.current_slice_index)
            state.current_slice_index += 1
        if outcome.target_state == "BLOCKED":
            state.blocked_reasons.extend(outcome.diagnostics or [f"blocked:{state.state}"])
        self.store.save(state)
        return state

    @staticmethod
    def _completion_gate_passed(state: GreenfieldRunState, outcome: GreenfieldOutcome) -> bool:
        verification = outcome.verification_ref or state.verification_ref
        convergence = outcome.convergence_decision or state.convergence_decision
        return bool(verification and convergence in {"continue", "complete"})


def _dump_state(state: GreenfieldRunState) -> dict:
    payload = asdict(state)
    payload["transitions"] = [asdict(item) for item in state.transitions]
    return payload
