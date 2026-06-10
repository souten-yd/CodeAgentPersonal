"""PIR-1 durable Blueprint lifecycle tests."""

from __future__ import annotations

from agent.architecture_blueprint.contracts import (
    BlueprintActivationRequest,
    BlueprintCreateRequest,
    BlueprintGetRequest,
    BlueprintGetRevisionRequest,
    BlueprintReviewRequest,
)
from agent.architecture_blueprint.lifecycle import ACTIVE
from agent.architecture_blueprint.module import ArchitectureBlueprintModuleImpl
from agent.architecture_blueprint.store import BlueprintStore


def test_blueprint_active_status_survives_reopen(tmp_path) -> None:
    db = tmp_path / "blueprint.db"
    module = ArchitectureBlueprintModuleImpl(BlueprintStore(db))
    created = module.create(BlueprintCreateRequest(project_id="p1", workspace_id="w1"))
    module.review(
        BlueprintReviewRequest(
            project_id="p1", blueprint_id=created.blueprint_id, revision_id=created.revision_id
        )
    )
    active = module.activate(
        BlueprintActivationRequest(
            project_id="p1", blueprint_id=created.blueprint_id, revision_id=created.revision_id
        )
    )
    module._store.close()

    reopened = ArchitectureBlueprintModuleImpl(BlueprintStore(db))
    generic_active = reopened.get_active(BlueprintGetRequest(project_id="p1", workspace_id="w1"))
    by_revision = reopened.get_revision(
        BlueprintGetRevisionRequest(
            project_id="p1", blueprint_id=created.blueprint_id, revision_id=created.revision_id
        )
    )
    reopened._store.close()

    assert active.status == ACTIVE
    assert generic_active is not None and generic_active.revision_id == created.revision_id
    assert generic_active.status == ACTIVE
    assert by_revision.status == ACTIVE

