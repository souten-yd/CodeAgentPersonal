import json
from pathlib import Path


def test_vue_09_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    for key in [
        'vue_next_build_artifact_policy_defined', 'vue_next_smoke_route_policy_defined',
        'vue_next_build_artifact_required', 'vue_next_dist_required_for_route',
        'vue_next_raw_source_serving_allowed', 'vue_next_smoke_route',
        'vue_next_smoke_route_enabled', 'vue_next_smoke_route_policy',
        'vue_next_static_mount_decision', 'vue_next_static_mount_strategy',
        'vue_next_dist_strategy_defined', 'vue_next_dist_dir',
        'vue_next_serves_raw_vite_source', 'vue_next_route', 'vue_next_route_mounted'
    ]:
        assert key in m
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_mutation_endpoints_enabled'] is False
    assert m['vue_next_action_buttons_enabled'] is False
    assert m['vue_next_backend_authoritative'] is True
    assert m['vue_next_source_of_truth'] is False
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
    assert m['vue_next_route_mounted'] is False
    assert m['vue_next_smoke_route_enabled'] is False
