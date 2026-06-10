"""PIR-1 durable DigitalTwinModuleImpl tests."""

from __future__ import annotations

from agent.project_intelligence.contracts import ProjectIdentity
from agent.project_twin.facade import (
    OpenTwinRequest,
    RefreshTwinRequest,
    TwinHealthRequest,
    TwinQueryRequest,
    TwinReadiness,
)
from agent.project_twin.module import DigitalTwinModuleImpl


def _identity(workspace_id: str = "w1") -> ProjectIdentity:
    return ProjectIdentity(project_id="p1", workspace_id=workspace_id, project_path="/repo")


def test_twin_revision_survives_close_reopen(tmp_path) -> None:
    db = tmp_path / "twin.db"
    twin = DigitalTwinModuleImpl(db)
    opened = twin.open_project(OpenTwinRequest(project=_identity()))
    refreshed = twin.refresh(RefreshTwinRequest(project=_identity(), changed_paths=["app.py"]))
    twin.close()

    reopened = DigitalTwinModuleImpl(db)
    health = reopened.health(TwinHealthRequest(project_id="p1", workspace_id="w1"))
    query = reopened.query(TwinQueryRequest(project_id="p1", workspace_id="w1", refs=["file://app.py"]))
    reopened.close()

    assert opened.readiness == TwinReadiness.READY
    assert health.readiness == TwinReadiness.READY
    assert health.twin_revision_id == refreshed.twin_revision_id
    assert [item.ref for item in query.items] == ["file://app.py"]


def test_refresh_failure_retains_prior_active_revision(tmp_path) -> None:
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    twin.open_project(OpenTwinRequest(project=_identity()))
    first = twin.refresh(RefreshTwinRequest(project=_identity(), changed_paths=["a.py"]))
    failed = twin.refresh(
        RefreshTwinRequest(
            project=_identity(),
            changed_paths=["b.py"],
            expected_revision_id="not-the-current-head",
        )
    )
    health = twin.health(TwinHealthRequest(project_id="p1", workspace_id="w1"))
    twin.close()

    assert failed.readiness == TwinReadiness.DEGRADED
    assert failed.twin_revision_id == first.twin_revision_id
    assert health.twin_revision_id == first.twin_revision_id

