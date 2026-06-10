"""PI-11 Blueprint generation, review, and validation tests.

Acceptance criteria (implementation plan PI-11):
- vague structural plans are rejected;
- empty-project Blueprint includes exact materialization targets;
- existing small change produces a Change Blueprint rather than a full redesign;
- validation is deterministic where possible;
- review diagnostics are machine-readable.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import (
    BlueprintElement,
    BlueprintRevision,
)
from agent.architecture_blueprint.generator import (
    BlueprintSpec,
    FileSpec,
    decide_scope,
    generate_blueprint,
)
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.architecture_blueprint.validator import (
    DEPENDENCY_CYCLE,
    REQUIREMENT_UNCOVERED,
    VAGUE_PLAN,
    validate_blueprint,
)


def _greenfield_spec() -> BlueprintSpec:
    return BlueprintSpec(
        requirements=["R1", "R2"],
        files=[
            FileSpec(path="app/models.py", requirement_ids=["R1"], acceptance=["defines User"]),
            FileSpec(path="app/service.py", requirement_ids=["R2"], depends_on=["app/models.py"],
                     acceptance=["implements create_user"]),
        ],
        entrypoint="app/main.py", build_command="pip install -e .",
        start_command="uvicorn app.main:app", test_command="pytest -q",
    )


# --- Scope decision ----------------------------------------------------------

def test_scope_decision() -> None:
    assert decide_scope("empty", 0) == "full_project"
    assert decide_scope("greenfield_partial", 2) == "full_project"
    assert decide_scope("existing", 1) == "change_set"
    assert decide_scope("repair", 1) == "repair"


# --- Empty-project Blueprint has exact materialization targets ----------------

def test_greenfield_blueprint_has_exact_targets_and_validates() -> None:
    bp = generate_blueprint(project_id="p1", workspace_id="w1", spec=_greenfield_spec(),
                            project_mode="empty")
    assert bp.scope == "full_project"
    files = [e for e in bp.elements if e.element_type == "file"]
    # exact file manifest with concrete materialization targets (planned bp:// -> file://).
    assert {e.name for e in files} == {"app/models.py", "app/service.py"}
    assert all(e.canonical_ref.startswith("bp://") for e in bp.elements)
    assert all(e.expected_actual_refs and e.expected_actual_refs[0].startswith("file://") for e in files)
    # execution contracts present.
    types = {e.element_type for e in bp.elements}
    assert "entrypoint" in types and "test_contract" in types

    report = validate_blueprint(bp)
    assert report.valid is True, [d.code for d in report.diagnostics]
    # dependency order: models before service.
    assert report.topological_order.index("el:app/models.py") < report.topological_order.index("el:app/service.py")


# --- Existing small change -> Change Blueprint, not redesign ------------------

def test_existing_small_change_is_change_set() -> None:
    spec = BlueprintSpec(requirements=["R9"],
                         files=[FileSpec(path="svc.py", requirement_ids=["R9"], acceptance=["fix bug"])])
    bp = generate_blueprint(project_id="p1", workspace_id="w1", spec=spec, project_mode="existing")
    assert bp.scope == "change_set"
    # A change_set is not padded with a full execution-contract redesign.
    assert all(e.element_type == "file" for e in bp.elements)
    assert validate_blueprint(bp).valid is True


# --- Vague plans rejected ----------------------------------------------------

def test_vague_plan_rejected() -> None:
    vague = BlueprintRevision(
        blueprint_id="b", revision_id="r", project_id="p1", scope="change_set",
        selected_architecture=planner_decision("d", "t", [], "", []),
        elements=[BlueprintElement(element_id="e1", canonical_ref="bp://stuff",
                                   element_type="component")],  # no acceptance / no actual target
    )
    report = validate_blueprint(vague)
    assert report.valid is False
    assert VAGUE_PLAN in {d.code for d in report.diagnostics}


# --- Requirement coverage + cycle detection ----------------------------------

def test_requirement_coverage_gap_detected() -> None:
    spec = BlueprintSpec(requirements=["R1", "R2"],
                         files=[FileSpec(path="a.py", requirement_ids=["R1"], acceptance=["x"])])
    bp = generate_blueprint(project_id="p1", workspace_id="w1", spec=spec, project_mode="existing")
    report = validate_blueprint(bp)
    assert report.valid is False
    cov = next(d for d in report.diagnostics if d.code == REQUIREMENT_UNCOVERED)
    assert "R2" in cov.refs


def test_dependency_cycle_detected() -> None:
    dec = planner_decision("d", "t", [], "", [])
    bp = BlueprintRevision(
        blueprint_id="b", revision_id="r", project_id="p1", scope="change_set",
        selected_architecture=dec,
        elements=[
            BlueprintElement(element_id="a", canonical_ref="bp://a", element_type="file",
                             depends_on_element_ids=["b"], acceptance_criteria=["x"]),
            BlueprintElement(element_id="b", canonical_ref="bp://b", element_type="file",
                             depends_on_element_ids=["a"], acceptance_criteria=["y"]),
        ],
    )
    report = validate_blueprint(bp)
    assert report.valid is False
    assert DEPENDENCY_CYCLE in {d.code for d in report.diagnostics}


# --- Determinism + machine-readable diagnostics ------------------------------

def test_validation_is_deterministic() -> None:
    bp = generate_blueprint(project_id="p1", workspace_id="w1", spec=_greenfield_spec(),
                            project_mode="empty",
                            now=__import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc))
    r1 = validate_blueprint(bp)
    r2 = validate_blueprint(bp)
    assert [d.code for d in r1.diagnostics] == [d.code for d in r2.diagnostics]
    assert r1.topological_order == r2.topological_order


def test_diagnostics_are_machine_readable() -> None:
    spec = BlueprintSpec(requirements=["R1", "Rmissing"],
                         files=[FileSpec(path="a.py", requirement_ids=["R1"], acceptance=["x"])])
    bp = generate_blueprint(project_id="p1", workspace_id="w1", spec=spec, project_mode="existing")
    report = validate_blueprint(bp)
    for d in report.diagnostics:
        assert isinstance(d.code, str) and d.code  # stable code
        assert isinstance(d.refs, list)
