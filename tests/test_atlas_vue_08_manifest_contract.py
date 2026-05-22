import json
from pathlib import Path


def test_vue_08_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_route'] == ''
    assert m['vue_next_route_mounted'] is False
    assert m['vue_next_static_mount_strategy'] == 'dist_required'
    assert m['vue_next_dist_strategy_defined'] is True
    assert m['vue_next_dist_dir'] == 'web/atlas-next/dist'
    assert m['vue_next_serves_raw_vite_source'] is False
    assert m['vue_next_static_mount_decision'] == 'deferred_until_guarded_smoke_route'
    assert m['vue_next_static_mount_policy'] in {'docs/atlas_vue_migration_plan.md#safe-static-mount--dist-strategy','docs/atlas_vue_migration_plan.md#atlas-next-read-only-smoke-route--build-artifact-policy'}
    for k, v in {
        'vue_next_default_enabled': False,
        'vue_next_execution_enabled': False,
        'vue_next_mutation_endpoints_enabled': False,
        'vue_next_action_buttons_enabled': False,
        'vue_next_backend_authoritative': True,
        'vue_next_source_of_truth': False,
        'level1_execution_enabled': False,
        'autonomous_execution_enabled': False,
    }.items():
        assert m[k] == v
