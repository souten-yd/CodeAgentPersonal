"""PI-13 deterministic matcher and multidimensional evaluator tests.

Acceptance criteria (implementation plan PI-13):
- absent, partial, materialized, observed, verified, divergent, blocked, stale are distinct;
- file existence does not imply behavior verification;
- stale evidence cannot satisfy mandatory verification;
- mismatches include explanation and evidence refs;
- matching is reproducible.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.architecture_blueprint.mapping import ActualEntry
from agent.project_convergence.evaluator import (
    ABSENT,
    BLOCKED,
    DIVERGENT,
    MATERIALIZED,
    OBSERVED,
    STALE,
    VERIFIED,
    VerificationEvidence,
    evaluate_convergence,
)

TWIN_REV = "twin-rev-1"


def _element(eid, name, *, expected, mandatory=True, interfaces=None):
    return BlueprintElement(element_id=eid, canonical_ref=f"bp://{name}", element_type="file",
                            name=name, expected_actual_refs=expected, mandatory=mandatory,
                            acceptance_criteria=["x"], properties={"interfaces": interfaces or []})


def _revision(elements):
    return BlueprintRevision(blueprint_id="b", revision_id="bprev-1", project_id="p1",
                             scope="full_project", selected_architecture=planner_decision("d", "t", [], "", []),
                             elements=elements)


def _evaluate(elements, snapshot, verification=None):
    return evaluate_convergence(_revision(elements), snapshot, project_id="p1", workspace_id="w1",
                                twin_revision_id=TWIN_REV, verification=verification or {})


def _state(report, eid):
    return next(r.state for r in report.element_results if r.blueprint_element_id == eid)


# --- All states are distinct -------------------------------------------------

def test_states_are_distinct() -> None:
    elements = [
        _element("e_blocked", "blocked.py", expected=["file://blocked.py"], mandatory=True),
        _element("e_absent", "absent.py", expected=["file://absent.py"], mandatory=False),
        _element("e_materialized", "mat.py", expected=["file://mat.py"]),
        _element("e_verified", "ver.py", expected=["file://ver.py"]),
        _element("e_observed", "obs.py", expected=["file://obs.py"]),
        _element("e_divergent", "div.py", expected=["file://div.py"]),
        _element("e_stale", "stale.py", expected=["file://stale.py"]),
    ]
    snapshot = [
        ActualEntry("file://mat.py", "mat.py", "file"),
        ActualEntry("file://ver.py", "ver.py", "file"),
        ActualEntry("file://obs.py", "obs.py", "file"),
        ActualEntry("file://div.py", "div.py", "file"),
        ActualEntry("file://stale.py", "stale.py", "file"),
    ]
    verification = {
        "file://ver.py": VerificationEvidence("passed", TWIN_REV, ["ev1"]),
        "file://obs.py": VerificationEvidence("observed", TWIN_REV),
        "file://div.py": VerificationEvidence("failed", TWIN_REV, ["ev2"]),
        "file://stale.py": VerificationEvidence("passed", "old-rev", ["ev3"]),
    }
    report = _evaluate(elements, snapshot, verification)
    assert _state(report, "e_blocked") == BLOCKED       # mandatory + unmatched
    assert _state(report, "e_absent") == ABSENT          # optional + unmatched
    assert _state(report, "e_materialized") == MATERIALIZED
    assert _state(report, "e_verified") == VERIFIED
    assert _state(report, "e_observed") == OBSERVED
    assert _state(report, "e_divergent") == DIVERGENT
    assert _state(report, "e_stale") == STALE
    # 7 distinct states present here (partial covered separately).
    assert len({_state(report, e.element_id) for e in elements}) == 7


# --- File existence != behavior verification ---------------------------------

def test_file_existence_does_not_imply_verified() -> None:
    elements = [_element("e", "a.py", expected=["file://a.py"])]
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    report = _evaluate(elements, snapshot)  # no verification evidence
    assert _state(report, "e") == MATERIALIZED  # present but not verified


def test_unavailable_does_not_verify() -> None:
    elements = [_element("e", "a.py", expected=["file://a.py"])]
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    verification = {"file://a.py": VerificationEvidence("unavailable", TWIN_REV)}
    report = _evaluate(elements, snapshot, verification)
    assert _state(report, "e") == MATERIALIZED  # unavailable never upgrades to verified


# --- Stale evidence cannot satisfy mandatory verification --------------------

def test_stale_evidence_cannot_satisfy_mandatory() -> None:
    elements = [_element("e", "a.py", expected=["file://a.py"], mandatory=True)]
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    verification = {"file://a.py": VerificationEvidence("passed", "different-rev", ["ev"])}
    report = _evaluate(elements, snapshot, verification)
    assert _state(report, "e") == STALE
    # The mandatory element remains a gap (not satisfied).
    assert any(g.blueprint_element_id == "e" for g in report.mandatory_gaps)
    assert "ev" in report.stale_evidence


# --- Mismatches include explanation + evidence -------------------------------

def test_mismatches_have_explanation_and_evidence() -> None:
    elements = [_element("e", "a.py", expected=["file://a.py"])]
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    verification = {"file://a.py": VerificationEvidence("failed", TWIN_REV, ["ev-fail"])}
    report = _evaluate(elements, snapshot, verification)
    res = report.element_results[0]
    assert res.state == DIVERGENT
    assert res.mismatches and res.mismatches[0].detail
    assert "ev-fail" in res.evidence_refs


# --- Reproducible ------------------------------------------------------------

def test_matching_is_reproducible() -> None:
    elements = [_element("e", "a.py", expected=["file://a.py"])]
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    r1 = _evaluate(elements, snapshot)
    r2 = _evaluate(elements, snapshot)
    assert [(x.blueprint_element_id, x.state) for x in r1.element_results] == \
           [(x.blueprint_element_id, x.state) for x in r2.element_results]


# --- Partial -----------------------------------------------------------------

def test_partial_when_some_expected_missing() -> None:
    el = _element("e", "a", expected=["file://a.py", "file://a_helper.py"])
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]  # helper missing
    report = _evaluate([el], snapshot)
    res = report.element_results[0]
    assert res.state == "partial"
    assert "file://a_helper.py" in res.missing_actual_refs
