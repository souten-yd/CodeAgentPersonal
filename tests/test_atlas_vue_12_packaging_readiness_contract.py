from pathlib import Path


def test_vue_12_packaging_readiness_policy_documented() -> None:
    docs = Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower()
    required = [
        'pr-atlas-vue-12 packaging/deployment readiness policy',
        'web/atlas-next',
        'npm install',
        'npm run build',
        'web/atlas-next/dist',
        'serve only dist artifacts',
        'not the source of truth',
        'build validation passes',
        'fail closed',
        'no raw vite source may be served',
        'no fallback to `ui.html` or `/` is allowed',
        'legacy ui remains available via /ui/',
        'guarded atlas next default',
        'get-only and metadata-only',
        'does not make vue default and does not enable execution',
    ]
    for token in required:
        assert token in docs
