"""PI-15 final completion and requirement-evidence integration tests.

Acceptance criteria (implementation plan PI-15):
- false-success scenarios fail rollup;
- unavailable evidence remains incomplete;
- delivery path is queryable for every mandatory requirement;
- legacy rollup remains fallback in off mode.
Required completion gates: 100% mandatory coverage, zero mandatory gaps, zero unresolved
decisions, zero failed verification, zero stale mandatory evidence, no unsafe halt.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.architecture_blueprint.mapping import ActualEntry
from agent.project_convergence.evaluator import VerificationEvidence, evaluate_convergence
from agent.project_intelligence.completion import evaluate_completion
from agent.project_twin.event_bridge import DeliveryTraceProjector
from agent.project_twin.facade import ProjectEventEnvelope

TWIN = "twin-1"


def _el(eid, name, *, req, expected):
    return BlueprintElement(element_id=eid, canonical_ref=f"bp://{name}", element_type="file",
                            name=name, expected_actual_refs=expected, requirement_ids=[req],
                            mandatory=True, acceptance_criteria=["x"])


def _rev(elements):
    return BlueprintRevision(blueprint_id="b", revision_id="bprev-1", project_id="p1",
                             scope="full_project", source_requirement_ids=["R1"],
                             selected_architecture=planner_decision("d", "t", [], "", []),
                             elements=elements)


def _delivery_terminals_for_R1() -> dict[str, list[str]]:
    """Build a real delivery trace (PI-5) and expose the terminal node kinds for R1."""
    proj = DeliveryTraceProjector()
    events = [
        ("requirement.confirmed", {"requirement_id": "R1"}, {}),
        ("plan_item.completed", {"requirement_ids": ["R1"]}, {"plan_item_id": "PI1"}),
        ("proposal.generated", {"proposal_id": "PR1"}, {"plan_item_id": "PI1"}),
        ("safe_apply.completed", {"proposal_id": "PR1", "applied_refs": ["file://a.py"]}, {"plan_item_id": "PI1"}),
        ("verification.completed", {"verification_id": "V1", "result": "passed",
                                    "evidence_refs": ["evidence://log"]}, {"plan_item_id": "PI1"}),
    ]
    for i, (et, payload, extra) in enumerate(events):
        proj.ingest(ProjectEventEnvelope(event_id=f"e{i}", event_type=et, project_id="p1",
                                         workspace_id="w1", idempotency_key=f"e{i}",
                                         plan_item_id=extra.get("plan_item_id"), payload=payload))
    trace = proj.get_trace("p1", "requirement://R1")
    return {"R1": [n.kind for n in trace.nodes]}


def _converged(verification):
    rev = _rev([_el("e1", "a.py", req="R1", expected=["file://a.py"])])
    snapshot = [ActualEntry("file://a.py", "a.py", "file")]
    report = evaluate_convergence(rev, snapshot, project_id="p1", workspace_id="w1",
                                  twin_revision_id=TWIN, verification=verification)
    return rev, report


# --- All gates pass -> complete ----------------------------------------------

def test_complete_when_all_gates_pass() -> None:
    rev, report = _converged({"file://a.py": VerificationEvidence("passed", TWIN, ["ev"])})
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=0, runtime_unavailable=0, unresolved_decisions=0, unsafe_halt=False,
        rollout_mode="active",
    )
    assert comp.complete is True
    assert all(g.passed for g in comp.gates)
    # delivery path for R1 reaches verification/evidence.
    assert comp.requirement_deliveries[0].has_delivery_path is True


# --- False success fails rollup ----------------------------------------------

def test_false_success_with_mandatory_gap_fails() -> None:
    # Element unmatched (empty snapshot) -> BLOCKED -> a real mandatory Blueprint gap.
    rev = _rev([_el("e1", "a.py", req="R1", expected=["file://a.py"])])
    report = evaluate_convergence(rev, [], project_id="p1", workspace_id="w1",
                                  twin_revision_id=TWIN, verification={})
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=0, runtime_unavailable=0, rollout_mode="active",
    )
    assert comp.complete is False
    assert comp.gate("zero_mandatory_blueprint_gaps").passed is False
    # A merely-materialized (present but unverified) mandatory element also blocks completion.
    rev2, report2 = _converged({})
    comp2 = evaluate_completion(
        convergence_report=report2, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=0, runtime_unavailable=0, rollout_mode="active",
    )
    assert comp2.complete is False
    assert comp2.gate("mandatory_requirement_coverage").passed is False


def test_failed_verification_fails_completion() -> None:
    rev, report = _converged({"file://a.py": VerificationEvidence("failed", TWIN, ["ev"])})
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=1, runtime_unavailable=0, rollout_mode="active",
    )
    assert comp.complete is False
    assert comp.gate("zero_failed_verification").passed is False


# --- Unavailable remains incomplete ------------------------------------------

def test_unavailable_remains_incomplete() -> None:
    rev, report = _converged({"file://a.py": VerificationEvidence("passed", TWIN, ["ev"])})
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=0, runtime_unavailable=1, rollout_mode="active",
    )
    assert comp.complete is False
    assert comp.gate("no_unavailable_required_evidence").passed is False


def test_stale_mandatory_evidence_blocks_completion() -> None:
    rev, report = _converged({"file://a.py": VerificationEvidence("passed", "old-rev", ["ev"])})
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=0, runtime_unavailable=0, rollout_mode="active",
    )
    assert comp.complete is False
    assert comp.gate("zero_stale_mandatory_evidence").passed is False


def test_unsafe_halt_blocks_completion() -> None:
    rev, report = _converged({"file://a.py": VerificationEvidence("passed", TWIN, ["ev"])})
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=0, runtime_unavailable=0, unsafe_halt=True, rollout_mode="active",
    )
    assert comp.complete is False and comp.gate("no_unsafe_halt").passed is False


# --- Delivery path required for every mandatory requirement ------------------

def test_missing_delivery_path_fails() -> None:
    rev, report = _converged({"file://a.py": VerificationEvidence("passed", TWIN, ["ev"])})
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]},
        delivery_terminal_kinds={"R1": ["requirement", "plan_item"]},  # no verification/evidence
        runtime_failed=0, runtime_unavailable=0, rollout_mode="active",
    )
    assert comp.complete is False
    assert comp.gate("delivery_path_for_every_mandatory_requirement").passed is False


# --- Legacy rollup remains fallback in off mode ------------------------------

def test_off_mode_defers_to_legacy_rollup() -> None:
    rev, report = _converged({})  # would fail the gates
    comp = evaluate_completion(
        convergence_report=report, mandatory_requirement_ids={"R1"},
        requirement_elements={"R1": ["e1"]}, delivery_terminal_kinds=_delivery_terminals_for_R1(),
        runtime_failed=0, runtime_unavailable=0, rollout_mode="off", legacy_complete=True,
    )
    assert comp.mode == "off"
    assert comp.complete is True  # legacy rollup authoritative in off mode
