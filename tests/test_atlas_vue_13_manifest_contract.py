import json
from pathlib import Path


def test_vue_13_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))

    assert m['vue_next_route_packaging_checkpoint'] == 'PR-ATLAS-VUE-13'
    assert m['vue_next_route_packaging_integration_defined'] is True
    assert m['vue_next_deploy_includes_dist_only'] is True
    assert m['vue_next_deploy_prebuilt_dist_required'] is True
    assert m['vue_next_runtime_build_allowed'] is False
    assert m['vue_next_server_startup_build_allowed'] is False
    assert m['vue_next_deploy_validation_required'] is True
    assert m['vue_next_deploy_validation_policy'] == 'validate_dist_before_packaging'
    assert m['vue_next_dist_artifact_source'] == 'prebuilt_web_atlas_next_dist'
    assert m['vue_next_dist_artifact_path'] == 'web/atlas-next/dist'
    assert m['vue_next_route_packaging_default_route_allowed'] is False
    assert m['vue_next_route_packaging_ui_html_fallback_allowed'] is False
    assert m['vue_next_route_packaging_root_fallback_allowed'] is False
    assert m['vue_next_route_packaging_raw_source_allowed'] is False

    assert m['vue_next_packaging_readiness_checkpoint'] == 'PR-ATLAS-VUE-12'
    assert m['vue_next_packaging_policy_defined'] is True
    assert m['vue_next_deployment_readiness_defined'] is True
    assert m['vue_next_dist_packaging_policy'] == 'dist_required_validated'
    assert m['vue_next_dist_source_of_truth'] is False
    assert m['vue_next_preview_diagnostics_endpoint'] == '/api/atlas/vue-next-preview/diagnostics'
    assert m['vue_next_default_enabled'] is True
    assert m['vue_next_default_not_execution_enable'] is True
    assert m['vue_next_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_mutation_endpoints_enabled'] is False
    assert m['vue_next_action_buttons_enabled'] is False
    assert m['vue_next_backend_authoritative'] is True
    assert m['vue_next_source_of_truth'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
