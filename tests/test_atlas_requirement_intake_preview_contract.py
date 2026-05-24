from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_requirement_intake_schema import AtlasRequirementIntakeRequest
from agent.atlas_requirement_intake_service import AtlasRequirementIntakeService


def test_requirement_intake_preview_is_read_only_and_backend_authoritative() -> None:
    result = AtlasRequirementIntakeService().preview(
        AtlasRequirementIntakeRequest(input="Build a planning-only Atlas workflow", source="vue_next")
    )

    assert result.schema_version == "atlas.requirement_intake_preview.v1"
    assert result.contract == "read_only_requirement_intake"
    assert result.status == "ready_for_planning"
    assert result.can_start_planning is True
    assert result.safety.runtime_level == "level_0_manual_only"
    assert result.safety.backend_workflow_state_authoritative is True
    assert result.safety.vue_source_of_truth is False
    assert result.safety.vue_execution_capability == "none"
    assert result.safety.mutation_performed is False
    assert result.safety.execution_performed is False
    assert result.safety.patch_apply_performed is False
    assert result.safety.git_operation_performed is False
    assert result.safety.autonomous_execution_enabled is False
    assert result.safety.self_modification_enabled is False


def test_requirement_intake_preview_blocks_empty_input_without_side_effects() -> None:
    result = AtlasRequirementIntakeService().preview(AtlasRequirementIntakeRequest(input="   ", source="atlas_workbench"))

    assert result.status == "blocked"
    assert result.can_start_planning is False
    assert "requirement_input_empty" in result.blocked_reasons
    assert result.safety.execution_performed is False
    assert result.safety.mutation_performed is False


def test_requirement_intake_preview_endpoint_contract() -> None:
    client = TestClient(main.app)
    response = client.post("/api/atlas/requirements/preview", json={"input": "Preview only", "source": "api"})

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "atlas.requirement_intake_preview.v1"
    assert body["contract"] == "read_only_requirement_intake"
    assert body["can_start_planning"] is True
    assert body["safety"]["runtime_level"] == "level_0_manual_only"
    assert body["safety"]["execution_performed"] is False
    assert body["safety"]["mutation_performed"] is False


def test_vue_requirement_input_uses_preview_before_plan_pool_creation() -> None:
    component = Path("web/atlas-next/src/components/RequirementInput.vue").read_text(encoding="utf-8")
    client = Path("web/atlas-next/src/api/atlasClient.ts").read_text(encoding="utf-8")

    assert "previewRequirementIntake" in component
    assert "Requirement preview:" in component
    assert "can_start_planning" in component
    assert "/api/atlas/requirements/preview" in client
    assert "read_only_preview: true" in client
    assert "vue_execution_capability: 'none'" in client


def test_requirement_intake_manifest_and_docs_lock_safety_boundary() -> None:
    manifest = Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8")
    docs = Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")

    assert '"atlas_requirement_intake_preview_contract": "atlas.requirement_intake_preview.v1"' in manifest
    assert '"atlas_requirement_intake_preview_read_only": true' in manifest
    assert '"atlas_requirement_intake_preview_execution_enabled": false' in manifest
    assert '"atlas_requirement_intake_preview_mutation_enabled": false' in manifest
    assert "Atlas Requirement intake preview foundation" in docs
    assert "Vue remains non-authoritative" in docs
