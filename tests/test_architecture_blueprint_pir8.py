"""PIR-8 durable Blueprint planning, review, and critical-decision tests."""

from __future__ import annotations

import pytest

from agent.architecture_blueprint.contracts import (
    BlueprintActivationRequest,
    BlueprintCreateRequest,
    BlueprintGetRequest,
    BlueprintReviewRequest,
)
from agent.architecture_blueprint.lifecycle import ACTIVE
from agent.architecture_blueprint.module import ArchitectureBlueprintModuleImpl
from agent.architecture_blueprint.store import BlueprintStore
from agent.architecture_blueprint.validator import validate_blueprint
from agent.project_intelligence.contracts import IntelligenceError, IntelligenceErrorCode


def test_pir8_existing_request_produces_scoped_change_blueprint_with_contracts(tmp_path) -> None:
    module = ArchitectureBlueprintModuleImpl(BlueprintStore(tmp_path / "blueprint.db"))
    created = module.create(
        BlueprintCreateRequest(
            project_id="p",
            workspace_id="w",
            project_mode="existing",
            source_requirement_ids=["R-user-search"],
            requirement_text="Add user search without redesigning the project",
            changed_files=["app/search.py"],
            api_routes=["GET /users/search"],
            schemas=["UserSearchResult"],
            config_keys=["SEARCH_LIMIT"],
            dependencies=["sqlite"],
            runtime_scenarios=["search returns filtered users"],
            nfrs=["p95 latency below 200ms"],
            preserve_behaviors=["existing user list endpoint remains unchanged"],
            commands={"test": "pytest tests/test_search.py -q"},
        )
    )

    revision = created.revision
    assert revision is not None
    assert revision.scope == "change_set"
    assert all(element.canonical_ref.startswith("bp://") for element in revision.elements)
    assert any(element.element_type == "api_route" for element in revision.elements)
    assert any(element.element_type == "schema" for element in revision.elements)
    assert any(element.element_type == "nfr" for element in revision.elements)
    assert validate_blueprint(revision).valid is True
    assert all(
        element.verification_contract_ids
        for element in revision.elements
        if element.mandatory and element.requirement_ids
    )

    review = module.review(
        BlueprintReviewRequest(
            project_id="p",
            blueprint_id=created.blueprint_id,
            revision_id=created.revision_id,
        )
    )
    assert review.valid is True
    reviews = module._store.list_reviews("p", created.blueprint_id)
    assert len(reviews) == 1
    assert reviews[0]["payload"]["valid"] is True
    module._store.close()


def test_pir8_greenfield_full_blueprint_activation_survives_restart(tmp_path) -> None:
    db = tmp_path / "blueprint.db"
    module = ArchitectureBlueprintModuleImpl(BlueprintStore(db))
    created = module.create(
        BlueprintCreateRequest(
            project_id="p",
            workspace_id="w",
            project_mode="empty",
            source_requirement_ids=["R-greenfield"],
            target_files=["app/main.py", "app/models.py"],
            commands={
                "entrypoint": "app/main.py",
                "build": "python -m compileall app",
                "start": "python app/main.py",
                "test": "pytest -q",
            },
        )
    )
    assert created.revision is not None
    assert created.revision.scope == "full_project"
    assert {element.element_type for element in created.revision.elements} >= {
        "file",
        "entrypoint",
        "command",
        "test_contract",
    }

    review = module.review(
        BlueprintReviewRequest(
            project_id="p",
            blueprint_id=created.blueprint_id,
            revision_id=created.revision_id,
        )
    )
    assert review.valid is True
    active = module.activate(
        BlueprintActivationRequest(
            project_id="p",
            blueprint_id=created.blueprint_id,
            revision_id=created.revision_id,
        )
    )
    assert active.status == ACTIVE
    module._store.close()

    reopened = ArchitectureBlueprintModuleImpl(BlueprintStore(db))
    persisted = reopened.get_active(BlueprintGetRequest(project_id="p", workspace_id="w"))
    assert persisted is not None
    assert persisted.revision_id == created.revision_id
    assert persisted.status == ACTIVE
    assert reopened._store.list_reviews("p", created.blueprint_id)[0]["payload"]["valid"] is True
    reopened._store.close()


def test_pir8_unresolved_critical_decision_blocks_review_and_activation(tmp_path) -> None:
    module = ArchitectureBlueprintModuleImpl(BlueprintStore(tmp_path / "blueprint.db"))
    created = module.create(
        BlueprintCreateRequest(
            project_id="p",
            workspace_id="w",
            project_mode="existing",
            scope="full_project",
            target_files=["app/main.py"],
        )
    )
    assert created.revision is not None
    assert created.revision.scope == "change_set"
    assert created.revision.unresolved_decisions

    review = module.review(
        BlueprintReviewRequest(
            project_id="p",
            blueprint_id=created.blueprint_id,
            revision_id=created.revision_id,
        )
    )
    assert review.valid is False
    assert review.unresolved_decisions
    assert any(diag.code == IntelligenceErrorCode.BLUEPRINT_DECISION_REQUIRED for diag in review.diagnostics)
    with pytest.raises(IntelligenceError) as exc:
        module.activate(
            BlueprintActivationRequest(
                project_id="p",
                blueprint_id=created.blueprint_id,
                revision_id=created.revision_id,
            )
        )
    assert exc.value.code == IntelligenceErrorCode.BLUEPRINT_DECISION_REQUIRED
    module._store.close()
