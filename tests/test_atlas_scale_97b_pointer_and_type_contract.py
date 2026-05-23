from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def test_scale_97b_docs_pointer_and_track_state() -> None:
    stale = 'Planned UI track: return to PR-ATLAS-SCALE-97 automation track'
    for path in DOCS:
        text = Path(path).read_text(encoding='utf-8')
        assert ('Completed automation PR: PR-ATLAS-SCALE-99' in text)
        assert 'Current automation track: PR-ATLAS-SCALE-100' in text
        assert 'Next automation track: PR-ATLAS-SCALE-100' in text
        assert 'next work is PR-ATLAS-SCALE-100' in text
        assert stale not in text


def test_scale_97b_readiness_evidence_required_type_is_string() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert 'evidence_required: string' in text
    assert 'evidence_required: boolean' not in text
