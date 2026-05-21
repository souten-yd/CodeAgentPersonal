from pathlib import Path


def test_autonomous_execution_readiness_policy_contract() -> None:
    p = Path('docs/atlas_autonomous_execution_readiness_policy.md')
    assert p.exists()
    t = p.read_text(encoding='utf-8')

    for s in [
        'This policy does not enable autonomous execution',
        'Current Atlas state remains Level 0',
        'Future PRs must explicitly move levels',
        'Snapshot / Restore Gate',
        'resolved data_root',
        'Patch Transaction Gate',
        'transaction has file list, diff summary, risk class, and rollback metadata',
        'Risk Classification Gate',
        'Verification Allowlist Gate',
        'Dry-run and Approval Gate',
        'Rollback Readiness Gate',
        'Artifact Capture Gate',
        'Stop / Kill Switch Gate',
        'Loop Bound Gate',
        'Remote Git Gate',
        'Self-Improvement Gate',
        'Level 0: Manual only',
        'Level 1: Guarded single-step automation candidate',
        'Level 2: Guarded bounded loop candidate',
        'Level 3: Autonomous implementation loop candidate',
        'Level 4: Self-improvement candidate',
        'execute all',
        'auto continue',
        'automatic safe_apply',
        'automatic verification',
        'automatic retry',
        'automatic rollback',
        'automatic patch generation',
        'git push',
        'git pull',
        'git clone',
        'direct merge',
        'EXECUTE ONE ACTION',
        'dry-run-first',
        'Backend workflow state is authoritative',
        'ThinUI remains supervision layer',
        'CLI should use the same backend workflow contract',
        'self-improving CodeAgentPersonal / KasaneCore',
    ]:
        assert s in t
