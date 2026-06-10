"""Final completion and requirement-evidence integration (PI-15).

Integrates Convergence into the final rollup WITHOUT replacing canonical verification
authority: completion is an advisory gate over evidence already produced by the canonical
verification/runtime systems. It never marks anything passed, never converts unavailable to
complete, and in ``off`` rollout mode it defers to the legacy rollup result.

Completion requires ALL gates: 100% mandatory requirement coverage, zero mandatory Blueprint
gaps, zero unresolved critical decisions, zero failed required verification, zero stale
mandatory evidence, no unsafe halt — and no unavailable required evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.project_convergence.contracts import ConvergenceReport
from agent.project_convergence.evaluator import STALE, VERIFIED


@dataclass
class CompletionGate:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class RequirementDelivery:
    requirement_id: str
    has_delivery_path: bool
    verified: bool
    terminal_kinds: list[str] = field(default_factory=list)


@dataclass
class CompletionReport:
    complete: bool
    mode: str
    gates: list[CompletionGate] = field(default_factory=list)
    requirement_deliveries: list[RequirementDelivery] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def gate(self, name: str) -> CompletionGate:
        return next(g for g in self.gates if g.name == name)


# Public summary of a delivery trace (decoupled from PI-5 internals): a list of node kinds
# reachable from the requirement is enough to know the path reaches verification/evidence.
def _reaches_verification(terminal_kinds: list[str]) -> bool:
    return any(k in ("verification", "evidence") for k in terminal_kinds)


def evaluate_completion(
    *,
    convergence_report: ConvergenceReport,
    mandatory_requirement_ids: set[str],
    requirement_elements: dict[str, list[str]],
    delivery_terminal_kinds: dict[str, list[str]],
    runtime_failed: int,
    runtime_unavailable: int,
    unresolved_decisions: int = 0,
    unsafe_halt: bool = False,
    rollout_mode: str = "active",
    legacy_complete: bool = False,
) -> CompletionReport:
    """Evaluate the completion gates. In ``off`` mode, defer to the legacy rollup."""
    results = {r.blueprint_element_id: r for r in convergence_report.element_results}

    # per-requirement delivery + verification
    deliveries: list[RequirementDelivery] = []
    coverage_ok = True
    delivery_ok = True
    for rid in sorted(mandatory_requirement_ids):
        elements = requirement_elements.get(rid, [])
        terminal = delivery_terminal_kinds.get(rid, [])
        has_path = _reaches_verification(terminal)
        verified = bool(elements) and all(
            results.get(eid) and results[eid].state == VERIFIED for eid in elements
        )
        deliveries.append(RequirementDelivery(rid, has_path, verified, terminal))
        if not elements or not verified:
            coverage_ok = False
        if not has_path:
            delivery_ok = False

    mandatory_stale = [
        r.blueprint_element_id for r in convergence_report.element_results if r.state == STALE
    ]

    gates = [
        CompletionGate("mandatory_requirement_coverage", coverage_ok,
                       "every mandatory requirement maps to a verified element"),
        CompletionGate("zero_mandatory_blueprint_gaps", len(convergence_report.mandatory_gaps) == 0,
                       f"{len(convergence_report.mandatory_gaps)} mandatory gaps"),
        CompletionGate("zero_unresolved_decisions", unresolved_decisions == 0,
                       f"{unresolved_decisions} unresolved decisions"),
        CompletionGate("zero_failed_verification", runtime_failed == 0,
                       f"{runtime_failed} failed verifications"),
        CompletionGate("zero_stale_mandatory_evidence", not mandatory_stale,
                       f"stale: {mandatory_stale}"),
        CompletionGate("no_unsafe_halt", not unsafe_halt, "unsafe halt condition"),
        CompletionGate("no_unavailable_required_evidence", runtime_unavailable == 0,
                       f"{runtime_unavailable} unavailable observations (remain incomplete)"),
        CompletionGate("delivery_path_for_every_mandatory_requirement", delivery_ok,
                       "each mandatory requirement has a queryable delivery path"),
    ]

    diagnostics = [f"{g.name}: {g.detail}" for g in gates if not g.passed]

    if rollout_mode == "off":
        # Off mode: Convergence is advisory only; the legacy rollup remains authoritative.
        return CompletionReport(complete=legacy_complete, mode="off", gates=gates,
                                requirement_deliveries=deliveries,
                                diagnostics=["off mode: legacy rollup authoritative"] + diagnostics)

    complete = all(g.passed for g in gates)
    return CompletionReport(complete=complete, mode=rollout_mode, gates=gates,
                            requirement_deliveries=deliveries, diagnostics=diagnostics)
