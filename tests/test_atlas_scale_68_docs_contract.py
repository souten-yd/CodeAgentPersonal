from pathlib import Path

def _active(text:str)->str:
    i=text.lower().find('current pr')
    return text[i:i+4000] if i!=-1 else text

def test_scale_68_docs_contract():
    docs=['docs/atlas_development_handoff.md','docs/atlas_unified_autopilot_checkpoint.md','docs/atlas_autopilot_current_status.md','docs/atlas_autopilot_scale_master_plan.md','docs/atlas_scale_master_roadmap.md']
    blob='\n'.join(Path(d).read_text() for d in docs)
    assert 'PR-ATLAS-SCALE-68' in blob
    assert 'PR-ATLAS-SCALE-69' in blob
    assert 'PR-ATLAS-SCALE-67B' in blob
    assert 'Verification Recommendation' in blob and 'Planner Packaging v2' in blob
    assert ('advisory-only' in blob.lower()) or ('advisory only' in blob.lower())
    assert ('not executed' in blob.lower()) or ('no execution' in blob.lower())
    active='\n'.join(_active(Path(d).read_text()) for d in docs)
    assert 'Next PR' in active and 'PR-ATLAS-SCALE-69' in active
