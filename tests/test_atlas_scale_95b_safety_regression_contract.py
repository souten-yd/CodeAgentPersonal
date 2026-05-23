from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_95b_docs_do_not_enable_execution_language() -> None:
    enabled_phrases = [
        'execute-all enabled',
        'auto-continue enabled',
        'autonomous execution enabled',
        'Level-1 execution enabled',
        'Vue execution capability enabled',
    ]
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8').lower()
        for phrase in enabled_phrases:
            assert phrase not in text


def test_scale_95b_runtime_and_execution_flags_stay_disabled_contract() -> None:
    text = Path('app/atlas/workflow_state_contract.py').read_text(encoding='utf-8')
    assert '"runtime_level": "level_0_manual_only"' in text
    assert '"level1_execution_enabled": False' in text
    assert '"autonomous_execution_enabled": False' in text

    client_text = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    for forbidden in (
        '/api/atlas/level1/execute',
        '/api/atlas/level1/dry-run',
        '/api/atlas/level1/approve',
        '/api/atlas/level1/apply',
        '/api/atlas/level1/verify',
        '/api/atlas/level1/rollback',
        '/api/atlas/level1/retry',
        '/api/atlas/level1/continue',
    ):
        assert forbidden not in client_text
