from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_development_handoff.md',
]


def _text(path: str) -> str:
    return Path(path).read_text(encoding='utf-8').lower()


def test_vue_12_pointer_alignment_present() -> None:
    docs = '\n'.join(_text(path) for path in DOCS)
    assert 'pr-atlas-vue-11 completed' in docs
    assert 'completed ui pr: pr-atlas-vue-12' in docs
    assert 'current ui track: pr-atlas-vue-13' in docs
    assert 'current automation track remains pr-atlas-scale-93' in docs
    assert 'existing ui.html remains default' in docs
    assert 'parallel/read-only/not default' in docs
    assert 'backend workflow_state remains authoritative' in docs
    assert 'vue execution capability remains none' in docs
