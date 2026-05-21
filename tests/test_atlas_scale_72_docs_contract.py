from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
    'docs/atlas_scale_master_roadmap.md',
]

def _active_blocks(text: str):
    out=[]
    for part in text.split('## '):
        if 'Active PR Pointer' in part or 'Current PR' in part or 'Restart Instructions' in part:
            out.append(part)
    return out

def test_scale_72_docs_active_pointer_and_restart_contract():
    combined='\n'.join(Path(p).read_text(encoding='utf-8') for p in DOCS)
    blocks='\n'.join(_active_blocks(combined))
    assert 'PR-ATLAS-SCALE-72' in blocks
    assert 'PR-ATLAS-SCALE-73: Atlas autonomous execution readiness checkpoint and roadmap consolidation' in combined
    for stale in ['Current next PR: PR-ATLAS-SCALE-70', 'Next implementation PR: PR-ATLAS-SCALE-70']:
        assert stale not in combined
    assert 'Current PR:\n- PR-ATLAS-SCALE-71\n\nNext PR:\n- PR-ATLAS-SCALE-72' not in blocks
    assert 'Current next PR (historical' in combined or 'historical' in combined.lower()

def test_scale_72_docs_manual_only_and_confirmation_facts_present():
    combined='\n'.join(Path(p).read_text(encoding='utf-8') for p in DOCS)
    for required in [
        'copy/export is manual-only',
        'Suggested commands are not executed',
        'Confirmation requirement remains unchanged',
        'EXECUTE ONE ACTION',
        'Dry-run-first remains required',
    ]:
        assert required in combined
