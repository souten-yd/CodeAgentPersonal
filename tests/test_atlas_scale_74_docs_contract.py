from pathlib import Path
DOCS=[
    Path('docs/atlas_development_handoff.md'),
    Path('docs/atlas_scale_master_roadmap.md'),
    Path('docs/atlas_unified_autopilot_checkpoint.md'),
    Path('docs/atlas_autopilot_current_status.md'),
    Path('docs/atlas_autopilot_scale_master_plan.md'),
]

def test_scale74_docs_contract():
    text='\n'.join(p.read_text(encoding='utf-8') for p in DOCS)
    assert 'Completed:\n- PR-ATLAS-SCALE-74' in text
    assert 'Current PR:\n- PR-ATLAS-SCALE-74' in text
    assert 'Next PR:\n- PR-ATLAS-SCALE-75: Hide advanced execution panels by default' in text
    for s in ['Automation-first ThinUI / CLI workflow shell','Backend workflow state is authoritative','CLI','replaceable','fully autonomous code agent','self-improving CodeAgentPersonal / KasaneCore','no execution semantics change','EXECUTE ONE ACTION','Dry-run-first remains required']:
      assert s in text
    assert 'Current next PR' not in text
