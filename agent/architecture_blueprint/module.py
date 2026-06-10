"""Concrete Architecture Blueprint Module (PI-10).

Implements the ``ArchitectureBlueprintModule`` facade over the immutable BlueprintStore and
the lifecycle rules. Revision content is immutable (store-enforced); a revise creates a
child; activation only moves an active pointer and never mutates content. The Blueprint
owns the approved target design only — it never reports actual implementation status.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agent.architecture_blueprint.contracts import (
    ArchitectureDecision,
    BlueprintActivationRequest,
    BlueprintCreateRequest,
    BlueprintGetRequest,
    BlueprintGetRevisionRequest,
    BlueprintElement,
    BlueprintResult,
    BlueprintReviewRequest,
    BlueprintReviewResult,
    BlueprintRevision,
    BlueprintRevisionRequest,
)
from agent.architecture_blueprint.lifecycle import (
    ACTIVE,
    APPROVED,
    PROPOSED,
    REJECTED,
    REVIEWED,
    SUPERSEDED,
    assert_planned_refs,
    assert_transition,
    planner_decision,
    validate_planned_refs,
    validate_scope,
)
from agent.architecture_blueprint.store import BlueprintStore
from agent.project_intelligence.contracts import (
    IntelligenceDiagnostic,
    IntelligenceError,
    IntelligenceErrorCode,
)


def _uid(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:12]}"


def _diag(message: str, code: IntelligenceErrorCode = IntelligenceErrorCode.BLUEPRINT_INVALID) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


class ArchitectureBlueprintModuleImpl:
    """Store-backed Blueprint facade with lifecycle and authority guards."""

    def __init__(self, store: BlueprintStore | None = None, *, now_fn: Callable[[], datetime] | None = None) -> None:
        self._store = store or BlueprintStore()
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        # operational lifecycle state (content is immutable in the store)
        self._status: dict[tuple[str, str], str] = {}

    # -- helpers --------------------------------------------------------------

    def _status_of(self, project_id: str, revision_id: str) -> str | None:
        return self._status.get((project_id, revision_id))

    def _load(self, project_id: str, revision_id: str) -> BlueprintRevision:
        row = self._store.get_revision(project_id, revision_id)
        if row is None:
            raise IntelligenceError(IntelligenceErrorCode.REVISION_NOT_FOUND, revision_id)
        rev = BlueprintRevision.model_validate(row["payload"])
        status = self._status_of(project_id, revision_id) or rev.status
        return rev.model_copy(update={"status": status})

    # -- facade ---------------------------------------------------------------

    def create(self, request: BlueprintCreateRequest) -> BlueprintResult:
        validate_scope(request.scope)
        blueprint_id = _uid("bp")
        revision_id = _uid("bprev")
        decision = planner_decision(_uid("dec"), "initial architecture", [], "", ["bootstrap"])
        revision = BlueprintRevision(
            blueprint_id=blueprint_id, revision_id=revision_id,
            project_id=request.project_id, workspace_id=request.workspace_id,
            scope=request.scope, source_requirement_ids=list(request.source_requirement_ids),
            source_twin_revision_id=request.source_twin_revision_id,
            project_mode=request.project_mode, status=PROPOSED,
            selected_architecture=decision, created_at=self._now(),
        )
        bad = validate_planned_refs(revision)
        if bad:
            return BlueprintResult(blueprint_id=blueprint_id, revision_id=revision_id, status="invalid",
                                   diagnostics=[_diag(f"planned elements use actual refs: {bad}")])
        self._store.save_revision(
            project_id=request.project_id, workspace_id=request.workspace_id,
            blueprint_id=blueprint_id, revision_id=revision_id,
            payload=revision.model_dump(mode="json"), status=PROPOSED,
            advance_head=False,
        )
        self._status[(request.project_id, revision_id)] = PROPOSED
        return BlueprintResult(blueprint_id=blueprint_id, revision_id=revision_id,
                               status=PROPOSED, revision=revision)

    def revise(self, request: BlueprintRevisionRequest) -> BlueprintResult:
        parent = self._load(request.project_id, request.parent_revision_id)
        child_id = _uid("bprev")
        child = parent.model_copy(update={
            "revision_id": child_id,
            "parent_revision_id": parent.revision_id,
            "status": PROPOSED,
            "created_at": self._now(),
            "activated_at": None,
        })
        self._store.save_revision(
            project_id=request.project_id, workspace_id=parent.workspace_id or "",
            blueprint_id=parent.blueprint_id, revision_id=child_id,
            payload=child.model_dump(mode="json"), status=PROPOSED,
            parent_revision_id=parent.revision_id, advance_head=False,
        )
        self._status[(request.project_id, child_id)] = PROPOSED
        return BlueprintResult(blueprint_id=parent.blueprint_id, revision_id=child_id,
                               status=PROPOSED, revision=child)

    def review(self, request: BlueprintReviewRequest) -> BlueprintReviewResult:
        rev = self._load(request.project_id, request.revision_id)
        diagnostics: list[IntelligenceDiagnostic] = []
        bad = validate_planned_refs(rev)
        if bad:
            diagnostics.append(_diag(f"planned elements use actual refs: {bad}"))
        unresolved = list(rev.unresolved_decisions)
        if unresolved:
            diagnostics.append(_diag("unresolved architecture decisions remain",
                                     IntelligenceErrorCode.BLUEPRINT_DECISION_REQUIRED))
        valid = not bad and not unresolved
        current = self._status_of(request.project_id, request.revision_id) or rev.status
        if valid:
            assert_transition(current, REVIEWED)
            self._status[(request.project_id, request.revision_id)] = APPROVED  # reviewed -> approved
        else:
            self._status[(request.project_id, request.revision_id)] = REVIEWED
        return BlueprintReviewResult(blueprint_id=rev.blueprint_id, revision_id=rev.revision_id,
                                     valid=valid, unresolved_decisions=unresolved, diagnostics=diagnostics)

    def activate(self, request: BlueprintActivationRequest) -> BlueprintRevision:
        rev = self._load(request.project_id, request.revision_id)
        current = self._status_of(request.project_id, request.revision_id) or rev.status
        if current != APPROVED:
            raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_INVALID,
                                    f"cannot activate from {current!r}; must be approved")
        assert_transition(current, ACTIVE)
        # supersede any currently active revision for this blueprint
        prior = self._store.get_active(request.project_id, rev.workspace_id or "", rev.blueprint_id)
        if prior is not None and prior["artifact_id"] != rev.revision_id:
            self._status[(request.project_id, prior["artifact_id"])] = SUPERSEDED
        self._store.activate_revision(project_id=request.project_id, workspace_id=rev.workspace_id or "",
                                      blueprint_id=rev.blueprint_id, revision_id=rev.revision_id)
        self._status[(request.project_id, rev.revision_id)] = ACTIVE
        return rev.model_copy(update={"status": ACTIVE, "activated_at": self._now()})

    def get_active(self, request: BlueprintGetRequest) -> BlueprintRevision | None:
        # The active revision is selected per blueprint (the store head per blueprint group).
        # The facade request carries no blueprint id, so callers that know the blueprint use
        # get_active_revision; this generic form returns None rather than guessing.
        return None

    def get_active_revision(self, project_id: str, workspace_id: str, blueprint_id: str) -> BlueprintRevision | None:
        row = self._store.get_active(project_id, workspace_id, blueprint_id)
        if row is None:
            return None
        rev = BlueprintRevision.model_validate(row["payload"])
        status = self._status_of(project_id, rev.revision_id) or rev.status
        return rev.model_copy(update={"status": status})

    def get_revision(self, request: BlueprintGetRevisionRequest) -> BlueprintRevision:
        return self._load(request.project_id, request.revision_id)
