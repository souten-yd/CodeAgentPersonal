from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
    'docs/atlas_thinui_readiness.md',
]

def test_scale77_doc_pointers_and_facts():
    combined='\n'.join(Path(p).read_text(encoding='utf-8') for p in DOCS)
    assert 'PR-ATLAS-SCALE-77' in combined
    assert 'Current implementation PR:\n- PR-ATLAS-SCALE-78' in combined
    assert 'Next implementation PR:\n- PR-ATLAS-SCALE-79' in combined
    for s in [
        'workflow state machine UI', 'derived from existing state',
        'at most one existing manual action per click', 'does not auto-continue',
        'does not execute all', 'dry-run-first', 'EXECUTE ONE ACTION',
        'Backend workflow state remains authoritative', 'replaceable and CLI-compatible',
        'fully autonomous code agent', 'Self-improving CodeAgentPersonal / KasaneCore',
        'out-of-order architecture checkpoint', 'does not imply PR-78〜79 are complete'
    ]:
        assert s in combined
    assert 'Current next PR' not in combined
