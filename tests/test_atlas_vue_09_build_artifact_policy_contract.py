import json
from pathlib import Path


def test_vue_09_build_artifact_policy_contract() -> None:
    package = json.loads(Path('web/atlas-next/package.json').read_text(encoding='utf-8'))
    assert 'build' in package.get('scripts', {})

    vite = Path('web/atlas-next/vite.config.ts').read_text(encoding='utf-8')
    assert "base: '/atlas-next/'" in vite

    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['vue_next_build_artifact_policy_defined'] is True
    assert manifest['vue_next_build_artifact_required'] is True
    assert manifest['vue_next_dist_required_for_route'] is True
    assert manifest['vue_next_dist_dir'] == 'web/atlas-next/dist'
    assert manifest['vue_next_raw_source_serving_allowed'] is False
    assert manifest['vue_next_serves_raw_vite_source'] is False

    docs = '\n'.join([
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower(),
    ])
    for required in [
        'generated artifact',
        'not the workflow source of truth',
        'raw vite source',
        'built-dist only',
    ]:
        assert required in docs
