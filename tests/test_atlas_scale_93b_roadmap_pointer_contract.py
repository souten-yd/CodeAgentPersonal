from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_93b_pointer_state_is_aligned_to_scale_94() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-93' in text
        assert 'Current automation track: PR-ATLAS-SCALE-94' in text
        assert 'Next automation track: PR-ATLAS-SCALE-94' in text
        assert ('Level-1 execution remains disabled' in text) or ('Level-1 backend skeleton remains disabled' in text)
        assert 'runtime remains level_0_manual_only' in text or 'Runtime remains level_0_manual_only' in text
        assert 'Autonomous execution remains disabled' in text
        assert 'workflow_state remains authoritative' in text
        assert 'Vue execution capability remains none' in text


def test_scale_94_is_described_as_disabled_backend_skeleton_candidate_only() -> None:
    text = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-SCALE-94: disabled backend skeleton candidate for future Level-1 guarded single-step execution' in text
    assert 'execution remains disabled by default' in text
    assert 'no runtime level change' in text
    assert 'no Vue execution controls' in text
