from pathlib import Path

def test_pr76c_docs_pointer_and_safety_contract():
    docs = [
        'docs/atlas_development_handoff.md',
        'docs/atlas_scale_master_roadmap.md',
        'docs/atlas_unified_autopilot_checkpoint.md',
        'docs/atlas_autopilot_current_status.md',
        'docs/atlas_autopilot_scale_master_plan.md',
        'docs/atlas_thinui_readiness.md',
    ]
    blob='\n'.join(Path(d).read_text(encoding='utf-8') for d in docs)
    for t in ['PR-ATLAS-SCALE-76C','PR-ATLAS-SCALE-77: Atlas workflow state machine UI','PR-ATLAS-SCALE-78: ThinUI contract tests and manifest-driven UI smoke','PR-76C fixes Diagnostics drawer structure','does not imply PR-77〜79 are complete','Backend workflow state is authoritative','fully autonomous code agent','self-improving CodeAgentPersonal / KasaneCore','Execution semantics remain unchanged','EXECUTE ONE ACTION remains required','Dry-run-first remains required']:
        assert t in blob
    assert 'Current next PR' not in blob
