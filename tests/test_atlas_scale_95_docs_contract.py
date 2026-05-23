from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_95_docs_pointer_and_safety_contract() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'PR-ATLAS-SCALE-95 completed' in text
        assert 'Current automation track: PR-ATLAS-SCALE-96' in text
        assert 'Next automation track: PR-ATLAS-SCALE-96' in text
        assert 'SCALE-95 added GET-only Level-1 readiness diagnostics only.' in text
        assert 'No execution endpoint is exposed.' in text
        assert 'Runtime remains level_0_manual_only' in text or 'runtime remains level_0_manual_only' in text
        assert 'Autonomous execution remains disabled' in text
        assert 'Backend workflow_state remains authoritative.' in text or 'backend workflow_state remains authoritative' in text
        assert 'Vue execution capability remains none.' in text or 'Vue execution capability remains none' in text
