from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
    'docs/atlas_thinui_readiness.md',
]

def test_scale_81_docs_contract() -> None:
    text = "\n".join(Path(d).read_text(encoding='utf-8') for d in DOCS)
    for s in [
        'PR-ATLAS-SCALE-81',
        'Current implementation PR:\n- PR-ATLAS-SCALE-82',
        'Next implementation PR:\n- PR-ATLAS-SCALE-83',
        'workspace snapshot / restore foundation',
        'resolved data_root',
        'Path("ca_data") direct writes remain forbidden',
        'Restore is manual-only',
        'Automatic rollback remains disabled',
        'Autonomous execution remains disabled',
        'Level 0 manual-only',
        'EXECUTE ONE ACTION remains required',
        'Dry-run-first remains required',
        'PR-80 remains an out-of-order architecture checkpoint',
        'fully autonomous code agent',
        'Self-improving CodeAgentPersonal / KasaneCore',
    ]:
        assert s in text

    for bad in ['PR-ATLAS-SCALE-82 completed', 'autonomous execution is enabled', 'rollback is automatic', 'Current next PR']:
        assert bad not in text
