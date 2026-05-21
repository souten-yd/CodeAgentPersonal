from pathlib import Path


def test_scale_87_docs_contract() -> None:
    files = [
        'docs/atlas_development_handoff.md', 'docs/atlas_scale_master_roadmap.md', 'docs/atlas_unified_autopilot_checkpoint.md',
        'docs/atlas_autopilot_current_status.md', 'docs/atlas_autopilot_scale_master_plan.md', 'docs/atlas_thinui_readiness.md',
        'docs/atlas_autonomous_execution_readiness_policy.md'
    ]
    text = "\n".join(Path(f).read_text(encoding='utf-8') for f in files)
    for s in [
        'PR-ATLAS-SCALE-87','Current implementation PR:\n- PR-ATLAS-SCALE-88','Next implementation PR:\n- PR-ATLAS-SCALE-89',
        'artifact capture gate consolidation','metadata-only','does not execute actions','does not create fake execution results',
        'does not create fake verification results','recorded explicitly','resolved data_root','plan','snapshot','patch transaction','rollback metadata',
        'risk classification','verification allowlist','dry-run approval gate','rollback readiness gate','warnings','recovery instructions',
        'Automatic artifact capture remains disabled','Automatic dry-run remains disabled','Automatic approval remains disabled',
        'Automatic execute remains disabled','Automatic verification remains disabled','Automatic command execution remains disabled',
        'Automatic safe_apply remains disabled','Automatic patch generation remains disabled','Automatic patch apply remains disabled',
        'Automatic restore remains disabled','Automatic rollback remains disabled','Autonomous execution remains disabled','Level 0 manual-only',
        'Primary CTA remains single existing manual action only','PR-80 remains an out-of-order architecture checkpoint','fully autonomous code agent',
        'Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope'
    ]:
        assert s in text
    for bad in ['PR-ATLAS-SCALE-88 completed', 'artifact capture executes actions', 'artifact capture fabricates']:
        assert bad not in text
