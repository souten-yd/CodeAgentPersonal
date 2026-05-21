from pathlib import Path


DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
]


def test_scale77_doc_pointers_and_facts():
    combined='\n'.join(Path(p).read_text(encoding='utf-8') for p in DOCS)
    assert 'PR-ATLAS-SCALE-77' in combined
    assert 'Current implementation PR:\n- PR-ATLAS-SCALE-79' in combined
    assert 'Next implementation PR:\n- PR-ATLAS-SCALE-81' in combined
    assert 'PR-ATLAS-SCALE-78' in combined
    assert 'PR-ATLAS-SCALE-80' in combined and 'out-of-order' in combined
    for phrase in ['may trigger at most one existing manual action per click', 'does not execute all', 'does not auto-continue', 'EXECUTE ONE ACTION', 'dry-run-first', 'Backend workflow state is authoritative']:
        assert phrase in combined
