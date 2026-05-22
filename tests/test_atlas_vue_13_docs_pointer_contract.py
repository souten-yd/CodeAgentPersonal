from pathlib import Path


def _text(path: str) -> str:
    return Path(path).read_text(encoding='utf-8').lower()


def test_vue_13_docs_pointers_and_policy() -> None:
    docs = '\n'.join([
        _text('docs/atlas_scale_master_roadmap.md'),
        _text('docs/atlas_vue_migration_plan.md'),
        _text('docs/atlas_thinui_readiness.md'),
        _text('docs/atlas_development_handoff.md'),
    ])
    required = [
                'pr-atlas-vue-13 completed',
        'completed ui prs: pr-atlas-vue-01 through pr-atlas-vue-15',
        'completed ui pr: pr-atlas-vue-13',
        'current atlas vue ui track state',
        'current ui track: pr-atlas-vue-16',
        'current automation track remains pr-atlas-scale-93',
        'existing `ui.html` remains default',
        'parallel/read-only/not default',
        'guarded/dist-backed/fail-closed',
        'get-only/metadata-only',
        'backend `workflow_state` remains authoritative',
        'no vue execution capability exists',
        'prebuilt dist artifacts only',
        'server startup must not run `npm install` or `npm run build` automatically',
        'generated dist is not source of truth',
        'source remains `web/atlas-next`',
        'dist remains `web/atlas-next/dist`',
        'deployment packaging may include `web/atlas-next/dist` only after validation passes',
        'no raw vite source serving',
        'no fallback to `/` or `ui.html`',
    ]
    for token in required:
        assert token in docs
