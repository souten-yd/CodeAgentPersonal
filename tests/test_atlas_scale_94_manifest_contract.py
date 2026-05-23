import json
from pathlib import Path


def test_scale_94_manifest_flags() -> None:
    manifest = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))

    required = {
        "level1_disabled_backend_skeleton_checkpoint": "PR-ATLAS-SCALE-94",
        "level1_backend_skeleton_enabled": True,
        "level1_backend_skeleton_execution_enabled": False,
        "level1_callable_execution_endpoint_enabled": False,
        "level1_route_exposed": False,
        "level1_metadata_only": True,
        "level1_readiness_result_available": True,
        "level1_disabled_blockers_reported": True,
        "level1_runtime_level_after_skeleton": "level_0_manual_only",
        "level1_vue_controls_after_skeleton": False,
        "level1_next_pr_may_add_readiness_diagnostics_get": True,
        "level1_next_pr_must_not_enable_execution": True,
        "runtime_level": "level_0_manual_only",
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
    }

    for key, value in required.items():
        assert key in manifest
        assert manifest[key] == value


def test_workflow_state_contract_remains_backend_authoritative_metadata_only() -> None:
    text = Path("app/atlas/workflow_state_contract.py").read_text(encoding="utf-8").lower()
    assert '"backend_workflow_state_authoritative": true' in text
    assert '"runtime_level": "level_0_manual_only"' in text
