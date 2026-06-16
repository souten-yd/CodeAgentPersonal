"""Autonomous self-improvement goal generation.

Mines deterministic signals into a ranked backlog of improvement goals the autonomous loop can pursue
on its own — no human picks the goal. Execution still goes through the existing safety gates (Proposal
/ Safe Apply / Verification, the self-modification guardrail for the system's own control modules, and
the approval gate for destructive/test-retirement actions), so "fully autonomous" applies to goal
SELECTION, not to bypassing any boundary.

Signals (all deterministic, no model):
- failing tests        -> fix the failure (highest priority: the suite is red).
- coverage gaps        -> add a focused test for an uncovered source symbol.
- recurring anti-patterns -> address a repeatedly-hit failure mode.
- TODO/FIXME markers   -> resolve a flagged debt.

Pure ranking/assembly; it proposes goals, it does not run them.
"""
from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import TwinControlPlaneModel

# Priority bands (higher runs first). A red suite outranks new coverage outranks debt.
_PRIORITY = {
    "fix_failing_test": 100,
    "address_anti_pattern": 80,
    "add_coverage": 60,
    "resolve_todo": 40,
}


class ImprovementGoal(TwinControlPlaneModel):
    goal_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)           # fix_failing_test | add_coverage | resolve_todo | address_anti_pattern
    description: str = Field(min_length=1)
    target_refs: list[str] = Field(default_factory=list)
    priority: int = 0
    source: str = ""
    self_protected: bool = False              # touches the system's own control modules -> needs approval
    evidence_refs: list[str] = Field(default_factory=list)


def _norm(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _is_self_protected(ref: str) -> bool:
    try:
        from agent.atlas_self_modification_policy import is_self_protected_path
        rel = str(ref)
        if rel.startswith("py://"):
            rel = rel[len("py://"):].split("#", 1)[0]
        return is_self_protected_path(rel)
    except Exception:
        return False


def generate_improvement_goals(
    *,
    failing_tests: Iterable[str] = (),
    coverage_gaps: Iterable[str] = (),
    todos: Iterable[dict] = (),
    anti_patterns: Iterable[dict] = (),
    max_goals: int = 50,
) -> list[ImprovementGoal]:
    """Assemble a ranked, de-duplicated improvement backlog from deterministic signals.

    ``todos``: ``[{"ref","text"}]``; ``anti_patterns``: ``[{"pattern_id","text","refs"}]``. Goals that
    touch the system's own control modules are marked ``self_protected`` (the execution loop must route
    them through approval, never auto-apply). Returns at most ``max_goals``, highest priority first."""
    goals: list[ImprovementGoal] = []

    for i, test in enumerate(_norm(failing_tests)):
        goals.append(ImprovementGoal(
            goal_id=f"goal_fix_{i}", kind="fix_failing_test",
            description=f"Fix the failing test {test} (make it pass without weakening it).",
            target_refs=[test], priority=_PRIORITY["fix_failing_test"], source="failing_tests",
            self_protected=_is_self_protected(test), evidence_refs=[test]))

    for i, ap in enumerate(anti_patterns):
        if not isinstance(ap, dict):
            continue
        refs = _norm(ap.get("refs") or [])
        goals.append(ImprovementGoal(
            goal_id=f"goal_antipattern_{i}", kind="address_anti_pattern",
            description=f"Address recurring failure mode: {str(ap.get('text') or ap.get('pattern_id') or '')[:160]}",
            target_refs=refs, priority=_PRIORITY["address_anti_pattern"], source="anti_pattern_memory",
            self_protected=any(_is_self_protected(r) for r in refs),
            evidence_refs=_norm([ap.get("pattern_id") or ""])))

    for i, sym in enumerate(_norm(coverage_gaps)):
        goals.append(ImprovementGoal(
            goal_id=f"goal_cov_{i}", kind="add_coverage",
            description=f"Add a focused test that exercises the currently-untested symbol {sym}.",
            target_refs=[sym], priority=_PRIORITY["add_coverage"], source="coverage_gap",
            self_protected=_is_self_protected(sym), evidence_refs=[sym]))

    for i, todo in enumerate(todos):
        if not isinstance(todo, dict):
            continue
        ref = str(todo.get("ref") or "").strip()
        goals.append(ImprovementGoal(
            goal_id=f"goal_todo_{i}", kind="resolve_todo",
            description=f"Resolve TODO/FIXME: {str(todo.get('text') or '')[:160]}",
            target_refs=[ref] if ref else [], priority=_PRIORITY["resolve_todo"], source="todo_marker",
            self_protected=_is_self_protected(ref), evidence_refs=[ref] if ref else []))

    # Highest priority first; stable within a band (preserves insertion order).
    goals.sort(key=lambda g: -g.priority)
    return goals[: max(0, max_goals)]
