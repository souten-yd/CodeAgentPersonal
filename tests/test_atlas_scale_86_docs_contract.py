from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
]

def test_scale_86_docs_contract() -> None:
    t = "\n".join(Path(p).read_text(encoding='utf-8') for p in DOCS)
    for s in [
        'PR-ATLAS-SCALE-86', 'Current implementation PR:\n- PR-ATLAS-SCALE-87', 'Next implementation PR:\n- PR-ATLAS-SCALE-88',
        'rollback readiness gate consolidation', 'metadata-only', 'does not restore files', 'does not execute rollback automatically',
        'does not authorize automatic execution', 'Restore remains manual-only', 'Automatic restore remains disabled',
        'Automatic rollback remains disabled', 'Snapshot manifest and rollback metadata are required', 'Restore plan is required',
        'manual snapshot restore', 'Automatic dry-run remains disabled', 'Automatic approval remains disabled',
        'Automatic execute remains disabled', 'Automatic verification remains disabled', 'Automatic command execution remains disabled',
        'Automatic safe_apply remains disabled', 'Automatic patch generation remains disabled', 'Automatic patch apply remains disabled',
        'Autonomous execution remains disabled', 'Level 0 manual-only', 'Primary CTA remains single existing manual action only',
        'PR-80 remains an out-of-order architecture checkpoint', 'fully autonomous code agent', 'Self-improving CodeAgentPersonal / KasaneCore remains',
    ]:
        assert s in t
    for bad in ['autonomous execution enabled', 'automatic rollback enabled', 'automatic restore enabled', 'PR-ATLAS-SCALE-87 completed', 'Current next PR']:
        assert bad not in t
