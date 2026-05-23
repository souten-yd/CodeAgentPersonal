from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_development_handoff.md',
]

REQUIRED_MARKERS = [
    'Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21',
    'Current UI track: Vue defaultization complete',
    'Planned UI track: return to PR-ATLAS-SCALE-103 automation track',
    '`/` is guarded Atlas Next default only when validated dist passes',
    'invalid/missing Vue dist falls back safely to legacy UI',
    'legacy UI remains available via /ui/',
    '`/atlas-next` remains guarded preview route',
    'backend workflow_state remains authoritative',
    'runtime remains level_0_manual_only',
    'Vue execution capability remains none',
    'VUE21 completed default-enable only, not execution-enable',
    'next work is PR-ATLAS-SCALE-104',
]

FORBIDDEN_STALE = [
    'Vue remains not default',
    'VUE21 is next',
    'Existing ui.html remains default until PR-ATLAS-VUE-21',
]


def _canonical_section(text: str) -> str:
    start = text.index('## Current Atlas Vue UI Track State')
    end = text.find('\n## ', start + 1)
    return text[start:] if end == -1 else text[start:end]


def test_docs_canonical_current_state_has_final_v21c_wording() -> None:
    for doc in DOCS:
        section = _canonical_section(Path(doc).read_text(encoding='utf-8'))
        for marker in REQUIRED_MARKERS:
            assert marker in section
        assert ('Current automation track: PR-ATLAS-SCALE-103' if 'Current automation track: PR-ATLAS-SCALE-103' in section else 'Current automation track: PR-ATLAS-SCALE-104') in section
        for marker in FORBIDDEN_STALE:
            assert marker not in section
