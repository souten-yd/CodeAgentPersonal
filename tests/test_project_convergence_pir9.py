"""PIR-9 Convergence evidence policy and revision correctness tests."""

from __future__ import annotations

from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.architecture_blueprint.mapping import ActualEntry
from agent.project_convergence.contracts import ConvergenceDecisionRequest, ConvergenceGetRequest, ConvergenceRequest
from agent.project_convergence.evaluator import (
    MATERIALIZED,
    VERIFIED,
    VerificationEvidence,
    evaluate_convergence,
)
from agent.project_convergence.module import ConvergenceModuleImpl


def _rev(elements: list[BlueprintElement]) -> BlueprintRevision:
    return BlueprintRevision(
        blueprint_id="bp",
        revision_id="bprev-9",
        project_id="p",
        workspace_id="w",
        scope="change_set",
        selected_architecture=planner_decision("d", "target", [], "", []),
        elements=elements,
    )


def _el(eid: str, element_type: str, actual_ref: str, *, vc: bool = True) -> BlueprintElement:
    return BlueprintElement(
        element_id=eid,
        canonical_ref=f"bp://{eid}",
        element_type=element_type,
        name=eid,
        expected_actual_refs=[actual_ref],
        acceptance_criteria=[f"{eid} accepted"],
        verification_contract_ids=[f"vc:{eid}"] if vc else [],
    )


def test_pir9_source_revision_is_not_compared_as_twin_revision() -> None:
    revision = _rev([_el("file", "file", "file://app.py")])
    report = evaluate_convergence(
        revision,
        [ActualEntry("file://app.py", "app.py", "file")],
        project_id="p",
        workspace_id="w",
        twin_revision_id="twin-rev-1",
        source_revision_id="source-rev-1",
        verification={"file://app.py": VerificationEvidence("passed", "source-rev-1", ["ev:file"])},
    )

    result = report.element_results[0]
    assert report.actual_twin_revision_id == "twin-rev-1"
    assert report.actual_source_revision_id == "source-rev-1"
    assert result.state == VERIFIED
    assert not report.stale_evidence


def test_pir9_mandatory_policy_requires_fresh_passing_evidence() -> None:
    revision = _rev([_el("file", "file", "file://app.py")])
    report = evaluate_convergence(
        revision,
        [ActualEntry("file://app.py", "app.py", "file")],
        project_id="p",
        workspace_id="w",
        twin_revision_id="twin",
        source_revision_id="source",
    )

    result = report.element_results[0]
    assert result.state == MATERIALIZED
    assert result.evidence_policy == "verified_test"
    assert "vc:file" in result.required_evidence_refs
    assert any(g.blueprint_element_id == "file" and "vc:file" in g.missing_refs for g in report.mandatory_gaps)


def test_pir9_unavailable_evidence_never_satisfies_policy() -> None:
    revision = _rev([_el("file", "file", "file://app.py")])
    report = evaluate_convergence(
        revision,
        [ActualEntry("file://app.py", "app.py", "file")],
        project_id="p",
        workspace_id="w",
        twin_revision_id="twin",
        source_revision_id="source",
        verification={"file://app.py": VerificationEvidence("unavailable", "source", ["ev:unavailable"])},
    )

    result = report.element_results[0]
    assert result.state == MATERIALIZED
    assert result.freshness == "unavailable"
    assert report.mandatory_gaps


def test_pir9_typed_dimension_mismatches_are_reported() -> None:
    revision = _rev(
        [
            _el("api", "api_route", "route://GET /users"),
            _el("schema", "schema", "table://users"),
            _el("state", "state", "state://workflow"),
            _el("resource", "resource", "resource://database:users"),
        ]
    )
    report = evaluate_convergence(
        revision,
        [
            ActualEntry("route://GET /users", "users", "file"),
            ActualEntry("table://users", "users", "route"),
            ActualEntry("state://workflow", "workflow", "event"),
            ActualEntry("resource://database:users", "users", "schema"),
        ],
        project_id="p",
        workspace_id="w",
        twin_revision_id="twin",
        source_revision_id="source",
    )
    dimensions = {m.dimension for result in report.element_results for m in result.mismatches}
    assert {"api_schema", "schema", "state", "resource"} <= dimensions
    assert len(report.mandatory_gaps) == 4


def test_pir9_reports_and_decisions_persist_with_revision_metadata(tmp_path) -> None:
    db = tmp_path / "convergence.db"
    revision = _rev([_el("file", "file", "file://app.py")])

    def load_blueprint(project_id: str, workspace_id: str, revision_id: str):
        return revision

    def load_actual(project_id: str, workspace_id: str, twin_revision_id: str):
        return [ActualEntry("file://app.py", "app.py", "file")]

    def load_verification(project_id: str, workspace_id: str, refs: list[str]):
        return {"file://app.py": VerificationEvidence("passed", "source-9", ["ev:file"])}

    module = ConvergenceModuleImpl(
        db,
        blueprint_loader=load_blueprint,
        actual_snapshot_loader=load_actual,
        verification_loader=load_verification,
    )
    report = module.evaluate(
        ConvergenceRequest(
            project_id="p",
            workspace_id="w",
            blueprint_revision_id="bprev-9",
            actual_twin_revision_id="twin-9",
            actual_source_revision_id="source-9",
            requirement_revision_id="req-9",
            mapping_revision_id="map-9",
            evidence_revision_id="evidence-9",
            verification_refs=["ev:file"],
        )
    )
    decision = module.decide(ConvergenceDecisionRequest(project_id="p", workspace_id="w", report_id=report.report_id))
    module.close()

    reopened = ConvergenceModuleImpl(db, blueprint_loader=load_blueprint)
    latest = reopened.get_latest(
        ConvergenceGetRequest(project_id="p", workspace_id="w", blueprint_revision_id="bprev-9")
    )
    decisions = reopened._store.list_decisions("p", report.report_id)
    reopened.close()

    assert latest is not None
    assert latest.actual_twin_revision_id == "twin-9"
    assert latest.actual_source_revision_id == "source-9"
    assert latest.requirement_revision_id == "req-9"
    assert latest.mapping_revision_id == "map-9"
    assert latest.evidence_revision_id == "evidence-9"
    assert decisions and decisions[0]["payload"]["action"] == decision.action
