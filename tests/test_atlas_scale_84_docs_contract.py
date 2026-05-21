from pathlib import Path

def test_scale84_docs_contract() -> None:
    files = ['docs/atlas_scale_master_roadmap.md', 'docs/atlas_development_handoff.md', 'docs/atlas_unified_autopilot_checkpoint.md', 'docs/atlas_autopilot_current_status.md', 'docs/atlas_autopilot_scale_master_plan.md', 'docs/atlas_thinui_readiness.md', 'docs/atlas_autonomous_execution_readiness_policy.md']
    t = "\n".join(Path(f).read_text(encoding='utf-8') for f in files)
    must = ['PR-ATLAS-SCALE-84', 'Current implementation PR:\n- PR-ATLAS-SCALE-85', 'Next implementation PR:\n- PR-ATLAS-SCALE-86', 'verification allowlist gate foundation', 'metadata-only', 'does not execute commands', 'future guarded/manual verification', 'suggestions only', 'no broad shell', 'no remote git', 'no package install', 'no destructive commands', 'no shell metacharacters', 'Automatic verification remains disabled', 'Automatic command execution remains disabled', 'Automatic safe_apply remains disabled', 'Automatic patch generation remains disabled', 'Automatic patch apply remains disabled', 'Automatic rollback remains disabled', 'Autonomous execution remains disabled', 'Level 0 manual-only', 'EXECUTE ONE ACTION remains required', 'Dry-run-first remains required', 'out-of-order architecture checkpoint', 'fully autonomous code agent', 'Self-improving CodeAgentPersonal / KasaneCore']
    for s in must:
        assert s in t
    assert 'PR-ATLAS-SCALE-85 completed' not in t
    assert 'allowlist authorizes execution' not in t
