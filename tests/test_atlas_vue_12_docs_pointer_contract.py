from pathlib import Path


def _text(path: str) -> str:
    return Path(path).read_text(encoding='utf-8').lower()


def test_vue_12_docs_pointers_and_tracks() -> None:
    docs = '\n'.join([
        _text('docs/atlas_scale_master_roadmap.md'),
        _text('docs/atlas_vue_migration_plan.md'),
        _text('docs/atlas_thinui_readiness.md'),
        _text('docs/atlas_development_handoff.md'),
    ])
    assert 'pr-atlas-vue-11 completed' in docs
    assert 'completed ui pr: pr-atlas-vue-12' in docs
    assert 'current ui track: pr-atlas-vue-13' in docs
    assert 'current automation track remains pr-atlas-scale-93' in docs
