from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_96_docs_track_pointers() -> None:
    for doc in DOCS:
        t = Path(doc).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-97' in t
        assert 'Current automation track: PR-ATLAS-SCALE-98' in t
        assert 'Next automation track: PR-ATLAS-SCALE-98' in t
        assert 'next work is PR-ATLAS-SCALE-98' in t
        assert 'next work is PR-ATLAS-SCALE-96' not in t
        assert 'Planned UI track: return to PR-ATLAS-SCALE-96 automation track' not in t
        assert 'SCALE-97 may add readiness UI display for gate-source mapping, not execution enable.' in t
        assert 'Level-1 execution remains disabled' in t
        assert 'runtime remains level_0_manual_only' in t or 'Runtime remains level_0_manual_only' in t
        assert 'Autonomous execution remains disabled' in t
        assert 'Vue execution capability remains none' in t
        assert 'Backend workflow_state remains authoritative' in t or 'backend workflow_state remains authoritative' in t
