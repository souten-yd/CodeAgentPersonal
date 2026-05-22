import json
from pathlib import Path


def test_vue_08_static_mount_deferred_contract() -> None:
    main_py = Path('main.py').read_text(encoding='utf-8').lower()
    assert '/atlas-next' not in main_py

    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_route'] == ''
    assert m['vue_next_route_mounted'] is False
    assert m['vue_next_static_mount_decision'] == 'deferred_until_guarded_smoke_route'
    assert m['vue_next_serves_raw_vite_source'] is False

    docs = '\n'.join([
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8').lower(),
    ])
    for required in [
        'static mount decision in this pr remains deferred',
        'raw vite source files must not be served as production ui',
        'future vue preview route must be `/atlas-next` only',
        'existing `ui.html` remains the default ui',
    ]:
        assert required in docs
