"""Architecture Blueprint lifecycle, scopes, diff, and authority guards (PI-10).

Pure rules over the Blueprint contracts:
- scopes (full_project / change_set / repair);
- the revision state machine and allowed transitions;
- a guard that a planned element is never represented with an Actual reference (ADR-PI-001);
- an authority guard that an LLM cannot fabricate a ``user_decision`` (contracts §4.3);
- a structural diff between a parent and child revision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.architecture_blueprint.contracts import (
    ArchitectureDecision,
    ArchitectureOption,
    BlueprintRevision,
)
from agent.project_intelligence.contracts import IntelligenceError, IntelligenceErrorCode

SCOPES = {"full_project", "change_set", "repair"}

# States.
PROPOSED = "proposed"
REVIEWED = "reviewed"
APPROVED = "approved"
ACTIVE = "active"
MATERIALIZING = "materializing"
SATISFIED = "satisfied"
DIVERGED = "diverged"
SUPERSEDED = "superseded"
REJECTED = "rejected"

STATES = {PROPOSED, REVIEWED, APPROVED, ACTIVE, MATERIALIZING, SATISFIED, DIVERGED, SUPERSEDED, REJECTED}
TERMINAL = {SUPERSEDED, REJECTED}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    PROPOSED: {REVIEWED, REJECTED},
    REVIEWED: {APPROVED, REJECTED, PROPOSED},
    APPROVED: {ACTIVE, REJECTED},
    ACTIVE: {MATERIALIZING, DIVERGED, SUPERSEDED},
    MATERIALIZING: {SATISFIED, DIVERGED, ACTIVE},
    SATISFIED: {SUPERSEDED, DIVERGED},
    DIVERGED: {MATERIALIZING, SUPERSEDED},
    SUPERSEDED: set(),
    REJECTED: set(),
}

# Reference namespaces.
_ACTUAL_SCHEMES = ("py://", "js://", "vue://", "file://", "module://", "pkg://", "route://", "table://")
_PLANNED_SCHEMES = ("bp://", "planned://")


def validate_scope(scope: str) -> None:
    if scope not in SCOPES:
        raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_INVALID, f"unknown scope {scope!r}")


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: str, target: str) -> None:
    if current not in STATES or target not in STATES:
        raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_INVALID, f"unknown state {current!r}->{target!r}")
    if not can_transition(current, target):
        raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_INVALID,
                                f"illegal transition {current!r}->{target!r}")


def validate_planned_refs(revision: BlueprintRevision) -> list[str]:
    """A planned element's canonical_ref must NOT use an Actual namespace (ADR-PI-001).

    Returns the list of offending element ids (empty when valid). ``expected_actual_refs``
    is the *only* place an Actual reference may appear (the planned->actual mapping).
    """
    bad: list[str] = []
    for el in revision.elements:
        if el.canonical_ref.startswith(_ACTUAL_SCHEMES):
            bad.append(el.element_id)
    return bad


def assert_planned_refs(revision: BlueprintRevision) -> None:
    bad = validate_planned_refs(revision)
    if bad:
        raise IntelligenceError(
            IntelligenceErrorCode.BLUEPRINT_INVALID,
            f"planned elements must not use Actual refs: {bad}",
        )


def planner_decision(decision_id: str, topic: str, options: list[ArchitectureOption],
                     selected_option_id: str, reasons: list[str]) -> ArchitectureDecision:
    """Build an architecture decision from planner/LLM output.

    The authority is forced to ``planner_recommendation``: an LLM can never fabricate a
    ``user_decision`` through this path.
    """
    return ArchitectureDecision(
        decision_id=decision_id, topic=topic, candidates=options,
        selected_option_id=selected_option_id, selection_reasons=reasons,
        authority="planner_recommendation",
    )


def user_decision(decision_id: str, topic: str, options: list[ArchitectureOption],
                  selected_option_id: str, *, confirmed_by_user: bool) -> ArchitectureDecision:
    """Build a decision with ``user_decision`` authority — only with explicit confirmation."""
    if not confirmed_by_user:
        raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_DECISION_REQUIRED,
                                "user_decision requires explicit user confirmation")
    return ArchitectureDecision(
        decision_id=decision_id, topic=topic, candidates=options,
        selected_option_id=selected_option_id, authority="user_decision",
    )


@dataclass
class BlueprintDiff:
    added_elements: list[str] = field(default_factory=list)
    removed_elements: list[str] = field(default_factory=list)
    changed_elements: list[str] = field(default_factory=list)


def diff_revisions(parent: BlueprintRevision, child: BlueprintRevision) -> BlueprintDiff:
    p = {e.element_id: e for e in parent.elements}
    c = {e.element_id: e for e in child.elements}
    added = sorted(set(c) - set(p))
    removed = sorted(set(p) - set(c))
    changed = sorted(
        eid for eid in set(p) & set(c)
        if p[eid].model_dump() != c[eid].model_dump()
    )
    return BlueprintDiff(added_elements=added, removed_elements=removed, changed_elements=changed)
