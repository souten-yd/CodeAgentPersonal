from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_93c_non_execution_and_authoritative_backend_markers() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'backend workflow_state remains authoritative' in text
        assert 'runtime remains level_0_manual_only' in text
        assert 'Level-1 execution remains disabled' in text
        assert 'Vue execution capability remains none' in text
        assert 'VUE21 completed default-enable only, not execution-enable' in text


def test_scale_93c_no_enabled_execution_wording_introduced() -> None:
    banned = [
        'execute-all enabled',
        'auto-continue enabled',
        'autonomous execution enabled',
        'level-1 execution enabled',
    ]
    for doc in DOCS:
        lower = Path(doc).read_text(encoding='utf-8').lower()
        for marker in banned:
            assert marker not in lower
