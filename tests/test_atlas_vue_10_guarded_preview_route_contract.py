import json
from pathlib import Path


def test_guarded_preview_route_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_route'] == '/atlas-next'
    assert m['vue_next_route_mounted'] is True
    assert m['vue_next_smoke_route_enabled'] is True
    assert m['vue_next_static_mount_decision'] == 'mounted_guarded_static_dist'

    route_text = Path('app/server.py').read_text(encoding='utf-8').lower()
    assert '/atlas-next' in route_text
    assert 'web/atlas-next/dist' in route_text
    assert 'web/atlas-next/src' not in route_text

    main_text = Path('main.py').read_text(encoding='utf-8').lower()
    assert 'configure_atlas_next_preview_route(app)' in main_text

    assert m['vue_next_default_enabled'] is True
    assert m['vue_next_default_requires_valid_dist'] is True
    assert m['vue_next_default_fail_closed'] is True
    assert m['vue_next_default_fallback_to_legacy_ui'] is True
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_mutation_endpoints_enabled'] is False
