"""PIR-1 project/workspace isolation across concrete modules."""

from __future__ import annotations

from agent.architecture_blueprint.contracts import (
    BlueprintActivationRequest,
    BlueprintCreateRequest,
    BlueprintGetRequest,
    BlueprintReviewRequest,
)
from agent.architecture_blueprint.module import ArchitectureBlueprintModuleImpl
from agent.architecture_blueprint.store import BlueprintStore
from agent.project_convergence.contracts import ConvergenceGetRequest, ConvergenceRequest
from agent.project_convergence.module import ConvergenceModuleImpl
from agent.project_intelligence.contracts import ProjectIdentity
from agent.project_twin.facade import OpenTwinRequest, RefreshTwinRequest, TwinQueryRequest
from agent.project_twin.module import DigitalTwinModuleImpl


def test_twin_workspaces_do_not_share_facts(tmp_path) -> None:
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    for workspace in ("w1", "w2"):
        twin.open_project(
            OpenTwinRequest(project=ProjectIdentity(project_id="p1", workspace_id=workspace, project_path="/repo"))
        )
    twin.refresh(
        RefreshTwinRequest(
            project=ProjectIdentity(project_id="p1", workspace_id="w1", project_path="/repo"),
            changed_paths=["only-w1.py"],
        )
    )
    w1 = twin.query(TwinQueryRequest(project_id="p1", workspace_id="w1", refs=["file://only-w1.py"]))
    w2 = twin.query(TwinQueryRequest(project_id="p1", workspace_id="w2", refs=["file://only-w1.py"]))
    twin.close()
    assert [item.ref for item in w1.items] == ["file://only-w1.py"]
    assert w2.items == []


def test_blueprint_active_pointer_is_workspace_scoped(tmp_path) -> None:
    module = ArchitectureBlueprintModuleImpl(BlueprintStore(tmp_path / "bp.db"))
    created = module.create(BlueprintCreateRequest(project_id="p1", workspace_id="w1"))
    module.review(
        BlueprintReviewRequest(
            project_id="p1", blueprint_id=created.blueprint_id, revision_id=created.revision_id
        )
    )
    module.activate(
        BlueprintActivationRequest(
            project_id="p1", blueprint_id=created.blueprint_id, revision_id=created.revision_id
        )
    )
    assert module.get_active(BlueprintGetRequest(project_id="p1", workspace_id="w1")) is not None
    assert module.get_active(BlueprintGetRequest(project_id="p1", workspace_id="w2")) is None
    module._store.close()


def test_convergence_latest_report_is_workspace_scoped(tmp_path) -> None:
    conv = ConvergenceModuleImpl(tmp_path / "conv.db")
    r1 = conv.evaluate(
        ConvergenceRequest(
            project_id="p1",
            workspace_id="w1",
            blueprint_revision_id="bp",
            actual_twin_revision_id="tw1",
        )
    )
    conv.evaluate(
        ConvergenceRequest(
            project_id="p1",
            workspace_id="w2",
            blueprint_revision_id="bp",
            actual_twin_revision_id="tw2",
        )
    )
    latest_w1 = conv.get_latest(ConvergenceGetRequest(project_id="p1", workspace_id="w1", blueprint_revision_id="bp"))
    latest_w2 = conv.get_latest(ConvergenceGetRequest(project_id="p1", workspace_id="w2", blueprint_revision_id="bp"))
    conv.close()
    assert latest_w1 is not None and latest_w1.report_id == r1.report_id
    assert latest_w2 is not None and latest_w2.actual_twin_revision_id == "tw2"

