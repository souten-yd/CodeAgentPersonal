import json
from pathlib import Path


def test_vue_08_dist_strategy_contract() -> None:
    package = json.loads(Path('web/atlas-next/package.json').read_text(encoding='utf-8'))
    assert 'build' in package.get('scripts', {})
    assert 'vite' in package['scripts']['build'].lower()
    tsconfig = Path('web/atlas-next/tsconfig.json').read_text(encoding='utf-8').lower()
    assert 'compileroptions' in tsconfig

    docs = '\n'.join([
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8').lower(),
    ])
    assert 'web/atlas-next/dist' in docs

    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['vue_next_dist_strategy_defined'] is True
    assert manifest['vue_next_dist_dir'] == 'web/atlas-next/dist'
    assert manifest['vue_next_static_mount_strategy'] == 'dist_required'

    vite = Path('web/atlas-next/vite.config.ts').read_text(encoding='utf-8')
    assert "base: '/atlas-next/'" in vite
