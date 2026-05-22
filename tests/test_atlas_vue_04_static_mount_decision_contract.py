from pathlib import Path
import json


def test_vue_04_static_mount_decision_contract() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    decision = manifest['vue_next_static_mount_decision']
    assert decision in {'mounted_static_dist', 'deferred_no_dist_strategy'}

    if decision == 'mounted_static_dist':
        assert manifest['vue_next_route'] == '/atlas-next'
        assert manifest['vue_next_route_mounted'] is True
    else:
        assert manifest['vue_next_route'] == ''
        assert manifest['vue_next_route_mounted'] is False
        docs = (Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8') +
                Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8')).lower()
        assert 'static mount deferred' in docs
        assert 'dist' in docs

    assert manifest['vue_next_default_enabled'] is False
    assert manifest['vue_next_execution_enabled'] is False
    ui = Path('main.py').read_text(encoding='utf-8')
    assert '@app.get("/")' in ui
