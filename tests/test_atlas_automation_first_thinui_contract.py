from pathlib import Path

DOCS=[
 Path('docs/atlas_scale_master_roadmap.md'),
 Path('docs/atlas_thinui_readiness.md'),
]

def test_automation_first_contract_language():
    text='\n'.join(p.read_text(encoding='utf-8') for p in DOCS)
    for s in [
        'Automation-first', 'CLI', 'replaceable', 'Backend workflow state is authoritative',
        'future CLI', 'future replacement UI', 'full-auto controller', 'must not encode execution decisions',
        'legacy/debug/advanced surfaces', 'fully autonomous code agent', 'self-improving CodeAgentPersonal / KasaneCore',
    ]:
        assert s in text
