"""Blueprint Plan Compiler and planning envelope (PI-16).

Turns Actual/Blueprint/Convergence state into a deterministic PlanPool through a stable
planning package. Per ADR-PI-008, deterministic code owns identity, dependency order,
requirement mapping, completed-item preservation, and target normalization; an LLM may
propose semantic grouping/strategy on top, never identity bookkeeping.

Phases: architecture / delivery / repair. Completed items are never recreated; a
downstream-only replan preserves completed items. The planning package records the
Blueprint, Actual-Twin, Convergence and context-manifest references (ADR-PI-012); old
PlanPool records load with defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.architecture_blueprint.contracts import BlueprintRevision

# Planning phases.
ARCHITECTURE = "architecture"
DELIVERY = "delivery"
REPAIR = "repair"

# Item kinds.
CREATE_FILE = "create_file"
CREATE_STRUCTURE = "create_structure"
MODIFY = "modify"
REPAIR_ITEM = "repair"

_GREENFIELD_MODES = {"empty", "greenfield_partial"}
_STRUCTURE_TYPES = {"directory", "package", "component", "product"}


@dataclass
class PlanItemSpec:
    item_id: str
    kind: str
    blueprint_element_ids: list[str] = field(default_factory=list)
    requirement_ids: list[str] = field(default_factory=list)
    target_refs: list[str] = field(default_factory=list)  # expected_actual_refs
    depends_on: list[str] = field(default_factory=list)   # other item_ids
    convergence_criteria: list[str] = field(default_factory=list)
    status: str = "pending"


@dataclass
class CompiledPlan:
    planning_phase: str
    project_mode: str
    items: list[PlanItemSpec] = field(default_factory=list)
    blueprint_revision_id: str | None = None
    actual_twin_revision_id: str | None = None
    convergence_report_id: str | None = None
    context_manifest_id: str | None = None

    def item(self, item_id: str) -> PlanItemSpec | None:
        return next((i for i in self.items if i.item_id == item_id), None)

    def plan_pool_metadata(self) -> dict:
        """The PlanPool extension fields (contracts §7)."""
        return {
            "blueprint_revision_id": self.blueprint_revision_id,
            "actual_twin_revision_id": self.actual_twin_revision_id,
            "convergence_report_id": self.convergence_report_id,
            "context_manifest_id": self.context_manifest_id,
            "project_mode": self.project_mode,
        }


_PLAN_POOL_DEFAULTS = {
    "blueprint_revision_id": None, "actual_twin_revision_id": None,
    "convergence_report_id": None, "context_manifest_id": None,
    "planning_envelope_hash": None, "project_mode": "imported_unknown",
}


def load_plan_pool_metadata(record: dict) -> dict:
    """Read a (possibly legacy) PlanPool record; missing extension fields default cleanly."""
    return {**_PLAN_POOL_DEFAULTS, **(record or {})}


def _item_id(element_id: str) -> str:
    return f"item:{element_id}"


def _topological(elements) -> list[str]:
    ids = {e.element_id for e in elements}
    deps = {e.element_id: [d for d in e.depends_on_element_ids if d in ids] for e in elements}
    order: list[str] = []
    seen: set[str] = set()

    def visit(n: str, stack: set[str]):
        if n in seen or n in stack:
            return
        stack.add(n)
        for d in deps.get(n, []):
            visit(d, stack)
        stack.discard(n)
        seen.add(n)
        order.append(n)

    for eid in sorted(ids):
        visit(eid, set())
    return order


def _kind_for(element_type: str, project_mode: str) -> str:
    if project_mode == "repair":
        return REPAIR_ITEM
    if project_mode in _GREENFIELD_MODES:
        return CREATE_STRUCTURE if element_type in _STRUCTURE_TYPES else CREATE_FILE
    return MODIFY


def compile_plan(
    revision: BlueprintRevision,
    *,
    project_mode: str,
    completed_item_ids: set[str] | None = None,
    replan_scope: set[str] | None = None,
    actual_twin_revision_id: str | None = None,
    convergence_report_id: str | None = None,
    context_manifest_id: str | None = None,
    phase: str | None = None,
) -> CompiledPlan:
    """Compile a Blueprint revision into a deterministic plan.

    - ``completed_item_ids``: these items are preserved, never recreated.
    - ``replan_scope`` (Blueprint element ids): only these elements (and any not-completed)
      are (re)compiled; completed items elsewhere are preserved unchanged.
    """
    completed = completed_item_ids or set()
    phase = phase or (REPAIR if project_mode == "repair" else
                      ARCHITECTURE if project_mode in _GREENFIELD_MODES else DELIVERY)
    by_id = {e.element_id: e for e in revision.elements}
    order = _topological(revision.elements)

    items: list[PlanItemSpec] = []
    for eid in order:
        el = by_id[eid]
        iid = _item_id(eid)
        # Preserve completed items (never recreate them).
        if iid in completed:
            items.append(PlanItemSpec(item_id=iid, kind=_kind_for(el.element_type, project_mode),
                                      blueprint_element_ids=[eid], requirement_ids=list(el.requirement_ids),
                                      target_refs=list(el.expected_actual_refs),
                                      depends_on=[_item_id(d) for d in el.depends_on_element_ids],
                                      status="completed"))
            continue
        # If a replan scope is set, only (re)compile items in scope; others stay as-is.
        if replan_scope is not None and eid not in replan_scope:
            items.append(PlanItemSpec(item_id=iid, kind=_kind_for(el.element_type, project_mode),
                                      blueprint_element_ids=[eid], requirement_ids=list(el.requirement_ids),
                                      target_refs=list(el.expected_actual_refs),
                                      depends_on=[_item_id(d) for d in el.depends_on_element_ids],
                                      status="preserved"))
            continue
        items.append(PlanItemSpec(
            item_id=iid, kind=_kind_for(el.element_type, project_mode),
            blueprint_element_ids=[eid], requirement_ids=list(el.requirement_ids),
            target_refs=list(el.expected_actual_refs),
            depends_on=[_item_id(d) for d in el.depends_on_element_ids],
            convergence_criteria=list(el.acceptance_criteria), status="pending",
        ))

    return CompiledPlan(
        planning_phase=phase, project_mode=project_mode, items=items,
        blueprint_revision_id=revision.revision_id, actual_twin_revision_id=actual_twin_revision_id,
        convergence_report_id=convergence_report_id, context_manifest_id=context_manifest_id,
    )


def requirement_element_coverage(plan: CompiledPlan, revision: BlueprintRevision) -> dict[str, list[str]]:
    """Requirement -> item ids, for completeness checks (every requirement is planned)."""
    coverage: dict[str, list[str]] = {rid: [] for rid in revision.source_requirement_ids}
    for item in plan.items:
        for rid in item.requirement_ids:
            coverage.setdefault(rid, []).append(item.item_id)
    return coverage
