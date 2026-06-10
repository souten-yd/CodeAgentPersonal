"""PI-14 convergence decision policy and incremental reevaluation tests.

Acceptance criteria (implementation plan PI-14):
- decision matrix tests cover all actions;
- incremental and full reports agree for affected elements;
- mandatory gap prevents complete;
- policy does not mutate Blueprint, PlanPool, or workspace.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import (
    BlueprintDecisionRequest,
    BlueprintElement,
    BlueprintRevision,
)
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.architecture_blueprint.mapping import ActualEntry
from agent.project_convergence.evaluator import (
    VerificationEvidence,
    evaluate_convergence,
    incremental_evaluate,
)
from agent.project_convergence.policy import (
    COMPLETE,
    CONTINUE,
    HALT_UNSAFE,
    REPAIR_CURRENT_ITEM,
    REPLAN_DOWNSTREAM,
    REQUEST_CRITICAL_DECISION,
    REVISE_BLUEPRINT,
    decide,
)

TWIN = "twin-1"


def _el(eid, name, *, expected, mandatory=True, depends=None, interfaces=None):
    return BlueprintElement(element_id=eid, canonical_ref=f"bp://{name}", element_type="file",
                            name=name, expected_actual_refs=expected, mandatory=mandatory,
                            depends_on_element_ids=depends or [], acceptance_criteria=["x"],
                            properties={"interfaces": interfaces or []})


def _rev(elements, *, unresolved=None):
    return BlueprintRevision(blueprint_id="b", revision_id="bprev-1", project_id="p1",
                             scope="full_project", selected_architecture=planner_decision("d", "t", [], "", []),
                             elements=elements, unresolved_decisions=unresolved or [])


def _report(rev, snapshot, verification=None):
    return evaluate_convergence(rev, snapshot, project_id="p1", workspace_id="w1",
                                twin_revision_id=TWIN, verification=verification or {})


# --- Decision matrix: all actions --------------------------------------------

def test_halt_unsafe() -> None:
    rev = _rev([_el("e", "a.py", expected=["file://a.py"])])
    d = decide(_report(rev, []), rev, unsafe_required=True)
    assert d.action == HALT_UNSAFE


def test_request_critical_decision() -> None:
    rev = _rev([_el("e", "a.py", expected=["file://a.py"])],
               unresolved=[BlueprintDecisionRequest(decision_id="dq1", topic="db")])
    d = decide(_report(rev, []), rev)
    assert d.action == REQUEST_CRITICAL_DECISION


def test_revise_blueprint_only_when_target_invalid() -> None:
    rev = _rev([_el("e", "a.py", expected=["file://a.py"])])
    d = decide(_report(rev, [ActualEntry("file://a.py", "a.py", "file")]), rev, target_invalid=True)
    assert d.action == REVISE_BLUEPRINT


def test_interface_divergence_replans_only_downstream() -> None:
    # e_base has an interface divergence; e_dep depends on it; e_other is unrelated.
    rev = _rev([
        _el("e_base", "base.py", expected=["file://base.py"], interfaces=["BaseProto"]),
        _el("e_dep", "dep.py", expected=["file://dep.py"], depends=["e_base"]),
        _el("e_other", "other.py", expected=["file://other.py"]),
    ])
    snapshot = [ActualEntry("file://base.py", "base.py", "file"),
                ActualEntry("file://dep.py", "dep.py", "file"),
                ActualEntry("file://other.py", "other.py", "file")]
    d = decide(_report(rev, snapshot), rev)
    assert d.action == REPLAN_DOWNSTREAM
    # affected = the divergent base + its downstream dependent, NOT the unrelated element.
    assert "e_base" in d.affected_blueprint_elements and "e_dep" in d.affected_blueprint_elements
    assert "e_other" not in d.affected_blueprint_elements


def test_runtime_divergence_repairs_current_item() -> None:
    rev = _rev([_el("e", "a.py", expected=["file://a.py"])])
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    verification = {"file://a.py": VerificationEvidence("failed", TWIN, ["ev"])}
    d = decide(_report(rev, snapshot, verification), rev, current_element_ids={"e"})
    assert d.action == REPAIR_CURRENT_ITEM and "e" in d.affected_blueprint_elements


def test_mandatory_gap_prevents_complete() -> None:
    rev = _rev([_el("e", "a.py", expected=["file://a.py"], mandatory=True)])
    d = decide(_report(rev, []), rev)  # nothing materialized -> blocked gap
    assert d.action == CONTINUE
    assert "e" in d.mandatory_gaps


def test_complete_when_all_mandatory_verified() -> None:
    rev = _rev([_el("e", "a.py", expected=["file://a.py"])])
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    verification = {"file://a.py": VerificationEvidence("passed", TWIN, ["ev"])}
    d = decide(_report(rev, snapshot, verification), rev)
    assert d.action == COMPLETE


def test_local_mismatch_does_not_revise_whole_blueprint() -> None:
    # A single runtime divergence yields repair/replan, never a whole-project redesign.
    rev = _rev([_el("e", "a.py", expected=["file://a.py"])])
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    verification = {"file://a.py": VerificationEvidence("failed", TWIN, ["ev"])}
    d = decide(_report(rev, snapshot, verification), rev)
    assert d.action != REVISE_BLUEPRINT


# --- Incremental agrees with full --------------------------------------------

def test_incremental_agrees_with_full_for_affected() -> None:
    rev = _rev([
        _el("e_a", "a.py", expected=["file://a.py"]),
        _el("e_b", "b.py", expected=["file://b.py"], depends=["e_a"]),
        _el("e_c", "c.py", expected=["file://c.py"]),
    ])
    snap_before = [ActualEntry("file://a.py", "a.py", "file"),
                   ActualEntry("file://c.py", "c.py", "file")]
    prior = _report(rev, snap_before)
    # a.py now gets passing verification (changed ref).
    snap_after = snap_before + [ActualEntry("file://b.py", "b.py", "file")]
    verification = {"file://a.py": VerificationEvidence("passed", TWIN, ["ev"])}
    inc = incremental_evaluate(rev, snap_after, changed_refs={"file://a.py", "file://b.py"},
                               prior_report=prior, project_id="p1", workspace_id="w1",
                               twin_revision_id=TWIN, verification=verification)
    full = evaluate_convergence(rev, snap_after, project_id="p1", workspace_id="w1",
                                twin_revision_id=TWIN, verification=verification)
    inc_states = {r.blueprint_element_id: r.state for r in inc.element_results}
    full_states = {r.blueprint_element_id: r.state for r in full.element_results}
    # affected elements agree with the full re-evaluation.
    for eid in ("e_a", "e_b"):
        assert inc_states[eid] == full_states[eid]
    assert "e_a" in inc.requirement_coverage["reevaluated"]


# --- Policy mutates nothing --------------------------------------------------

def test_policy_does_not_mutate_inputs() -> None:
    rev = _rev([_el("e", "a.py", expected=["file://a.py"])])
    report = _report(rev, [])
    before = rev.model_dump_json()
    report_before = report.model_dump_json()
    decide(report, rev)
    assert rev.model_dump_json() == before  # blueprint unchanged
    assert report.model_dump_json() == report_before  # report unchanged
