import json
from pathlib import Path


def test_vue_09_smoke_route_policy_contract() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['vue_next_smoke_route'] == '/atlas-next'
    assert manifest['vue_next_smoke_route_enabled'] is True
    assert manifest['vue_next_route'] == '/atlas-next'
    assert manifest['vue_next_route_mounted'] is True
    assert manifest['vue_next_static_mount_decision'] == 'mounted_guarded_static_dist'

    main_py = Path('main.py').read_text(encoding='utf-8').lower()
    assert 'configure_atlas_next_preview_route(app)' in main_py

    docs = '\n'.join([
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8').lower(),
    ])
    for required in [
        'future preview route must be `/atlas-next` only',
        'existing `ui.html` remains default',
        'fail closed',
        'must never replace `/`',
        'must never replace `/ui.html`',
        'read-only preview only',
        'no execution controls',
        'no mutation endpoint calls',
    ]:
        assert required in docs
