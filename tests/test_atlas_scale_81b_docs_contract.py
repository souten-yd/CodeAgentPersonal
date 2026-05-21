from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_81b_docs_contract() -> None:
    text = "\n".join(Path(d).read_text(encoding='utf-8') for d in DOCS)
    required = [
        'PR-ATLAS-SCALE-81B',
        'Current implementation PR:\n- PR-ATLAS-SCALE-82',
        'Next implementation PR:\n- PR-ATLAS-SCALE-83',
        'snapshot / restore path safety',
        'resolve under project_root',
        'Symlinks are skipped by default',
        'Symlink escapes are skipped / warned and not read',
        'resolve under snapshot_dir',
        'resolve under project_path',
        'delete_missing_before is plan-only / non-destructive',
        'Restore is manual-only',
        'Automatic rollback remains disabled',
        'Autonomous execution remains disabled',
        'Level 0 manual-only',
        'EXECUTE ONE ACTION remains required',
        'Dry-run-first remains required',
        'PR-80 remains an out-of-order architecture checkpoint',
        'fully autonomous code agent',
        'Self-improving CodeAgentPersonal / KasaneCore',
    ]
    for s in required:
        assert s in text

    for bad in [
        'autonomous execution is enabled',
        'rollback is automatic',
        'symlinks are followed',
        'delete_missing_before deletes files',
        'PR-ATLAS-SCALE-82 completed',
        'Current next PR',
    ]:
        assert bad not in text
