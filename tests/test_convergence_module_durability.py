"""PIR-1 durable ConvergenceModuleImpl tests."""

from __future__ import annotations

from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.architecture_blueprint.mapping import ActualEntry
from agent.project_convergence.contracts import (
    ConvergenceDecisionRequest,
    ConvergenceGetRequest,
    ConvergenceRequest,
)
from agent.project_convergence.evaluator import VerificationEvidence
from agent.project_convergence.module import ConvergenceModuleImpl


def _revision() -> BlueprintRevision:
    return BlueprintRevision(
        blueprint_id="bp",
        revision_id="bprev-1",
        project_id="p1",
        workspace_id="w1",
        scope="change_set",
        selected_architecture=planner_decision("d", "target", [], "", []),
        elements=[
            BlueprintElement(
                element_id="e1",
                canonical_ref="bp://app",
                element_type="file",
                name="app.py",
                expected_actual_refs=["file://app.py"],
                acceptance_criteria=["test passes"],
            )
        ],
    )


def test_convergence_report_and_decision_survive_reopen(tmp_path) -> None:
    db = tmp_path / "convergence.db"
    revision = _revision()

    def load_blueprint(project_id: str, workspace_id: str, revision_id: str):
        return revision if (project_id, workspace_id, revision_id) == ("p1", "w1", "bprev-1") else None

    def load_actual(project_id: str, workspace_id: str, twin_revision_id: str):
        assert twin_revision_id == "twin-1"
        return [ActualEntry("file://app.py", "app.py", "file")]

    def load_verification(project_id: str, workspace_id: str, refs: list[str]):
        return {"file://app.py": VerificationEvidence("passed", "twin-1", ["ev1"])}

    conv = ConvergenceModuleImpl(
        db,
        blueprint_loader=load_blueprint,
        actual_snapshot_loader=load_actual,
        verification_loader=load_verification,
    )
    report = conv.evaluate(
        ConvergenceRequest(
            project_id="p1",
            workspace_id="w1",
            blueprint_revision_id="bprev-1",
            actual_twin_revision_id="twin-1",
            verification_refs=["ev1"],
        )
    )
    decision = conv.decide(
        ConvergenceDecisionRequest(project_id="p1", workspace_id="w1", report_id=report.report_id)
    )
    conv.close()

    reopened = ConvergenceModuleImpl(db, blueprint_loader=load_blueprint)
    latest = reopened.get_latest(
        ConvergenceGetRequest(project_id="p1", workspace_id="w1", blueprint_revision_id="bprev-1")
    )
    reopened.close()

    assert report.element_results[0].state == "verified"
    assert decision.action == "complete"
    assert latest is not None and latest.report_id == report.report_id
    assert latest.actual_twin_revision_id == "twin-1"

