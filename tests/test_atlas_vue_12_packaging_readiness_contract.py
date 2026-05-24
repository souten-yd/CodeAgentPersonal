from pathlib import Path


def test_vue_12_packaging_policy_documented() -> None:
    docs = '\n'.join(
        Path(path).read_text(encoding='utf-8').lower()
        for path in [
            'docs/atlas_scale_master_roadmap.md',
            'docs/atlas_vue_migration_plan.md',
            'docs/atlas_thinui_readiness.md',
            'docs/atlas_development_handoff.md',
        ]
    )
    assert 'packaging/deployment policy (vue-12)' in docs
    assert 'vue source of truth remains `web/atlas-next`'.lower() in docs
    assert 'dist output remains `web/atlas-next/dist`'.lower() in docs
    assert '/atlas-next` may serve only dist artifacts'.lower() in docs
    assert 'generated dist is not the source of truth' in docs
    assert 'build validation passes' in docs
    assert 'missing or invalid dist must fail closed' in docs
    assert 'serving raw vite source is disallowed' in docs
    assert 'no fallback to `ui.html` or `/` is allowed' in docs
    assert 'does not make vue default and does not enable execution' in docs
