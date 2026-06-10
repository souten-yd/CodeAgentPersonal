"""Convergence decision policy (PI-14).

Converts an evaluated ConvergenceReport into one bounded next action WITHOUT executing it.
Deterministic rules precede any optional LLM advice. A local mismatch never triggers a
whole-project redesign; an interface change replans only affected downstream items; an
unsafe requirement never becomes automatic execution. The policy mutates nothing (no
Blueprint, PlanPool, or workspace writes).
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import BlueprintRevision
from agent.project_convergence.contracts import ConvergenceDecision, ConvergenceReport
from agent.project_convergence.evaluator import (
    BLOCKED,
    DIVERGENT,
    PARTIAL,
    STALE,
    VERIFIED,
)

# Actions (contracts §5.3).
CONTINUE = "continue"
COMPLETE = "complete"
REPAIR_CURRENT_ITEM = "repair_current_item"
REPLAN_DOWNSTREAM = "replan_downstream"
REVISE_BLUEPRINT = "revise_blueprint"
REQUEST_CRITICAL_DECISION = "request_critical_decision"
HALT_UNSAFE = "halt_unsafe"

_GAP_STATES = {BLOCKED, PARTIAL, STALE, "absent"}


def _downstream(revision: BlueprintRevision, element_ids: set[str]) -> set[str]:
    """Elements that (transitively) depend on any of element_ids."""
    dependents: dict[str, set[str]] = {}
    for el in revision.elements:
        for dep in el.depends_on_element_ids:
            dependents.setdefault(dep, set()).add(el.element_id)
    out: set[str] = set()
    frontier = list(element_ids)
    while frontier:
        cur = frontier.pop()
        for d in dependents.get(cur, set()):
            if d not in out:
                out.add(d)
                frontier.append(d)
    return out


def decide(
    report: ConvergenceReport,
    revision: BlueprintRevision,
    *,
    unsafe_required: bool = False,
    target_invalid: bool = False,
    current_element_ids: set[str] | None = None,
) -> ConvergenceDecision:
    """Deterministically choose the smallest valid next action."""
    current_element_ids = current_element_ids or set()
    results = {r.blueprint_element_id: r for r in report.element_results}

    # 1) unsafe requirement never becomes automatic execution.
    if unsafe_required:
        return ConvergenceDecision(action=HALT_UNSAFE, reason_codes=["unsafe_operation_required"])

    # 2) unresolved critical decisions in the blueprint.
    if revision.unresolved_decisions:
        return ConvergenceDecision(
            action=REQUEST_CRITICAL_DECISION,
            reason_codes=["unresolved_blueprint_decision"],
            affected_blueprint_elements=[],
        )

    divergent = {eid for eid, r in results.items() if r.state == DIVERGENT}
    interface_divergent = {
        eid for eid in divergent
        if any(m.dimension == "interface" for m in results[eid].mismatches)
    }
    runtime_divergent = divergent - interface_divergent

    # 3) target design itself invalid -> revise blueprint (NOT for a single local mismatch).
    if target_invalid:
        return ConvergenceDecision(action=REVISE_BLUEPRINT, reason_codes=["target_design_invalid"],
                                   affected_blueprint_elements=sorted(divergent))

    # 4) interface change -> replan only affected downstream items.
    if interface_divergent:
        affected = interface_divergent | _downstream(revision, interface_divergent)
        return ConvergenceDecision(
            action=REPLAN_DOWNSTREAM, reason_codes=["interface_divergence"],
            affected_blueprint_elements=sorted(affected),
            affected_plan_items=sorted(affected),
        )

    # 5) runtime failure on the current item -> local repair.
    if runtime_divergent:
        scope = runtime_divergent & current_element_ids or runtime_divergent
        return ConvergenceDecision(action=REPAIR_CURRENT_ITEM, reason_codes=["runtime_divergence"],
                                   affected_blueprint_elements=sorted(scope),
                                   affected_plan_items=sorted(scope))

    # 6) mandatory gaps remain -> keep going (cannot complete).
    mandatory_gap_ids = [g.blueprint_element_id for g in report.mandatory_gaps if g.blueprint_element_id]
    if mandatory_gap_ids:
        return ConvergenceDecision(action=CONTINUE, reason_codes=["mandatory_gaps_remain"],
                                   mandatory_gaps=sorted(mandatory_gap_ids))

    # 7) only a report with all mandatory element policies verified may become a
    # bounded complete candidate. Final completion remains owned by CompletionEvaluator.
    mandatory_ids = {el.element_id for el in revision.elements if el.mandatory}
    if mandatory_ids and all(eid in results and results[eid].state == VERIFIED for eid in mandatory_ids):
        return ConvergenceDecision(action=COMPLETE, reason_codes=["all_mandatory_verified"])

    return ConvergenceDecision(action=CONTINUE, reason_codes=["no_verified_evidence_yet"])
