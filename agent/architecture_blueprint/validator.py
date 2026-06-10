"""Blueprint validation (PI-11).

Deterministic validation of a Blueprint revision across the contract dimensions, returning
machine-readable diagnostics (stable codes). Vague structural plans are rejected; full
projects require an exact file manifest and execution contracts; dependency cycles and
planned-as-Actual refs are detected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.architecture_blueprint.contracts import BlueprintRevision
from agent.architecture_blueprint.lifecycle import validate_planned_refs

# Stable diagnostic codes (machine-readable).
REQUIREMENT_UNCOVERED = "requirement_uncovered"
VAGUE_PLAN = "vague_plan"
DEPENDENCY_CYCLE = "dependency_cycle"
MISSING_EXECUTION_CONTRACT = "missing_execution_contract"
UNRESOLVED_DECISION = "unresolved_decision"
PLANNED_USES_ACTUAL_REF = "planned_uses_actual_ref"
MISSING_FILE_MANIFEST = "missing_file_manifest"

_FILE_TYPES = {"file"}
_ENTRYPOINT_TYPES = {"entrypoint", "startup_contract"}
_TEST_TYPES = {"test_contract", "runtime_scenario"}


@dataclass
class Diagnostic:
    code: str
    message: str
    refs: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    valid: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)
    requirement_coverage: dict[str, list[str]] = field(default_factory=dict)


def _topological_order(elements) -> tuple[list[str], list[str]]:
    """Return (order, cycle_nodes). cycle_nodes non-empty means a dependency cycle."""
    ids = {e.element_id for e in elements}
    deps = {e.element_id: [d for d in e.depends_on_element_ids if d in ids] for e in elements}
    visited: dict[str, int] = {}  # 0=visiting, 1=done
    order: list[str] = []
    cycle: list[str] = []

    def visit(node: str, stack: set[str]) -> bool:
        state = visited.get(node)
        if state == 1:
            return True
        if node in stack:
            cycle.append(node)
            return False
        stack.add(node)
        for d in deps.get(node, []):
            if not visit(d, stack):
                return False
        stack.discard(node)
        visited[node] = 1
        order.append(node)
        return True

    for eid in sorted(ids):
        if visited.get(eid) != 1:
            if not visit(eid, set()):
                return [], cycle
    return order, []


def validate_blueprint(revision: BlueprintRevision) -> ValidationReport:
    diags: list[Diagnostic] = []
    elements = revision.elements
    element_types = {e.element_type for e in elements}

    # planned-vs-Actual
    bad_refs = validate_planned_refs(revision)
    if bad_refs:
        diags.append(Diagnostic(PLANNED_USES_ACTUAL_REF, "planned elements use Actual refs", bad_refs))

    # vague plan: no elements, or no mandatory element carries a concrete materialization target.
    concrete = [e for e in elements if e.canonical_ref and (e.expected_actual_refs or e.acceptance_criteria)]
    if not elements or not concrete:
        diags.append(Diagnostic(VAGUE_PLAN, "blueprint lacks concrete materialization targets"))

    # requirement coverage
    coverage: dict[str, list[str]] = {rid: [] for rid in revision.source_requirement_ids}
    for e in elements:
        for rid in e.requirement_ids:
            coverage.setdefault(rid, []).append(e.element_id)
    uncovered = [rid for rid in revision.source_requirement_ids if not coverage.get(rid)]
    if uncovered:
        diags.append(Diagnostic(REQUIREMENT_UNCOVERED, "requirements without a blueprint element", uncovered))

    # full_project needs an exact file manifest + execution contracts
    if revision.scope == "full_project":
        if not (_FILE_TYPES & element_types):
            diags.append(Diagnostic(MISSING_FILE_MANIFEST, "full_project requires file elements"))
        if not (_ENTRYPOINT_TYPES & element_types):
            diags.append(Diagnostic(MISSING_EXECUTION_CONTRACT, "missing entrypoint/startup contract"))
        if not (_TEST_TYPES & element_types) and not any(e.verification_contract_ids for e in elements):
            diags.append(Diagnostic(MISSING_EXECUTION_CONTRACT, "missing test/runtime contract"))

    # dependency order / cycles
    order, cycle = _topological_order(elements)
    if cycle:
        diags.append(Diagnostic(DEPENDENCY_CYCLE, "dependency cycle among elements", sorted(set(cycle))))

    # unresolved critical decisions
    if revision.unresolved_decisions:
        diags.append(Diagnostic(UNRESOLVED_DECISION, "unresolved critical decisions remain",
                                [d.decision_id for d in revision.unresolved_decisions]))

    valid = not diags
    return ValidationReport(valid=valid, diagnostics=diags, topological_order=order,
                            requirement_coverage=coverage)
