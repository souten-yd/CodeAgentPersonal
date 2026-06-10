"""PI-16 planning envelope and Blueprint Plan Compiler tests.

Acceptance criteria (implementation plan PI-16):
- empty project produces create-file/create-structure items;
- existing project produces scoped modify items;
- downstream-only replan preserves completed items;
- requirement and Blueprint element mappings are complete.
Plus: deterministic dependency order; PlanPool stores revision/manifest refs; old PlanPools
load with defaults.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.project_intelligence.plan_compiler import (
    ARCHITECTURE,
    CREATE_FILE,
    CREATE_STRUCTURE,
    DELIVERY,
    MODIFY,
    compile_plan,
    load_plan_pool_metadata,
    requirement_element_coverage,
)


def _el(eid, name, etype, *, req, depends=None, expected=None):
    return BlueprintElement(element_id=eid, canonical_ref=f"bp://{name}", element_type=etype,
                            name=name, requirement_ids=[req] if req else [],
                            depends_on_element_ids=depends or [],
                            expected_actual_refs=expected or [f"file://{name}"], acceptance_criteria=["x"])


def _rev(elements, reqs):
    return BlueprintRevision(blueprint_id="b", revision_id="bprev-1", project_id="p1",
                             scope="full_project", source_requirement_ids=reqs,
                             selected_architecture=planner_decision("d", "t", [], "", []),
                             elements=elements)


# --- Empty project -> create items + deterministic order ---------------------

def test_empty_project_creates_file_and_structure_items() -> None:
    rev = _rev([
        _el("e_pkg", "app", "package", req="R1", expected=[]),
        _el("e_models", "app/models.py", "file", req="R1", depends=["e_pkg"]),
        _el("e_service", "app/service.py", "file", req="R2", depends=["e_models"]),
    ], ["R1", "R2"])
    plan = compile_plan(rev, project_mode="empty")
    assert plan.planning_phase == ARCHITECTURE
    kinds = {i.item_id: i.kind for i in plan.items}
    assert kinds["item:e_pkg"] == CREATE_STRUCTURE
    assert kinds["item:e_models"] == CREATE_FILE
    # deterministic dependency order: pkg before models before service.
    order = [i.item_id for i in plan.items]
    assert order.index("item:e_pkg") < order.index("item:e_models") < order.index("item:e_service")


# --- Existing project -> scoped modify items ---------------------------------

def test_existing_project_modifies() -> None:
    rev = _rev([_el("e", "svc.py", "file", req="R1")], ["R1"])
    plan = compile_plan(rev, project_mode="existing")
    assert plan.planning_phase == DELIVERY
    assert all(i.kind == MODIFY for i in plan.items)


# --- Completed items preserved -----------------------------------------------

def test_completed_items_not_recreated() -> None:
    rev = _rev([
        _el("e_a", "a.py", "file", req="R1"),
        _el("e_b", "b.py", "file", req="R2", depends=["e_a"]),
    ], ["R1", "R2"])
    plan = compile_plan(rev, project_mode="empty", completed_item_ids={"item:e_a"})
    a = plan.item("item:e_a")
    b = plan.item("item:e_b")
    assert a.status == "completed"  # preserved, not recreated as pending
    assert b.status == "pending"


# --- Downstream-only replan preserves completed ------------------------------

def test_downstream_only_replan_preserves_completed_and_unscoped() -> None:
    rev = _rev([
        _el("e_a", "a.py", "file", req="R1"),
        _el("e_b", "b.py", "file", req="R2", depends=["e_a"]),
        _el("e_c", "c.py", "file", req="R3"),
    ], ["R1", "R2", "R3"])
    plan = compile_plan(rev, project_mode="existing",
                        completed_item_ids={"item:e_a"}, replan_scope={"e_b"})
    assert plan.item("item:e_a").status == "completed"   # completed preserved
    assert plan.item("item:e_b").status == "pending"     # in replan scope -> recompiled
    assert plan.item("item:e_c").status == "preserved"   # out of scope -> preserved


# --- Requirement + Blueprint element mappings complete -----------------------

def test_requirement_and_element_mappings_complete() -> None:
    rev = _rev([
        _el("e_a", "a.py", "file", req="R1"),
        _el("e_b", "b.py", "file", req="R2"),
    ], ["R1", "R2"])
    plan = compile_plan(rev, project_mode="empty")
    # every element has an item; every item maps to its element + requirement.
    assert {i.blueprint_element_ids[0] for i in plan.items} == {"e_a", "e_b"}
    coverage = requirement_element_coverage(plan, rev)
    assert coverage["R1"] and coverage["R2"]  # all requirements planned


# --- PlanPool metadata + legacy defaults -------------------------------------

def test_plan_pool_metadata_records_references() -> None:
    rev = _rev([_el("e", "a.py", "file", req="R1")], ["R1"])
    plan = compile_plan(rev, project_mode="empty", actual_twin_revision_id="tw1",
                        convergence_report_id="cv1", context_manifest_id="cm1")
    md = plan.plan_pool_metadata()
    assert md["blueprint_revision_id"] == "bprev-1"
    assert md["actual_twin_revision_id"] == "tw1"
    assert md["convergence_report_id"] == "cv1"
    assert md["context_manifest_id"] == "cm1"


def test_legacy_plan_pool_loads_with_defaults() -> None:
    md = load_plan_pool_metadata({"some_old_field": 1})
    assert md["blueprint_revision_id"] is None
    assert md["project_mode"] == "imported_unknown"
    assert md["some_old_field"] == 1
