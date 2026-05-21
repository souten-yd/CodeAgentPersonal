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
        'strict-gate',
        'unknown risk is not low risk',
        'Verification Allowlist Gate',
        'allowlist does not execute commands',
        'recommended commands remain suggestions only',
        'no broad shell',
        'no arbitrary command execution',
        'Dry-run and Approval Gate',
        'dry-run-first is mandatory',
        'EXECUTE ONE ACTION remains required',
        'explicit approval is mandatory for medium/high/strict risk',
        'strict_gate always requires explicit approval',
        'gate readiness does not execute automatically',
        'Rollback Readiness Gate',

        'rollback plan exists',
        'restore plan is required and must be valid',
        'restore remains manual-only',
        'automatic rollback requires a future explicit policy PR',
        'snapshot manifest and rollback metadata are required',
        'Artifact Capture Gate',
        'plan / intent summary',
        'patch transaction manifest',
        'dry-run result',
        'execution result',
        'verification plan',
        'verification result',
        'warnings and recovery instructions',
        'resolved data_root',

        'artifact capture is metadata-only in PR-87 and does not execute actions',
        'does not create fake execution results',
        'does not create fake verification results',
        'missing references are recorded explicitly',
        'Stop / Kill Switch Gate',
        'stop state must be visible in ThinUI/CLI',
        'no auto-continue after stop',
        'execute-all remains forbidden',
        'does not stop real jobs or kill processes',
        'Loop Bound Gate',
        'Remote Git Gate',
        'Self-Improvement Gate',
        'metadata-only self-improvement gate',
        'autonomous self-improvement remains disabled',
        'automatic self-modification remains disabled',
        'self-modification is strict-gate by default',
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


    for s in [
        'max actions per loop',
        'max retries',
        'max runtime',
        'max files changed',
        'max risk level',
        'No unbounded autonomous loop',
        'Auto-continue remains disabled',
        'Execute-all remains forbidden',
    ]:
        assert s in t



def test_remote_git_policy_scale_90_contract():
    text = open('docs/atlas_autonomous_execution_readiness_policy.md', encoding='utf-8').read().lower()
    for s in ['no git push','no git pull','no git clone','no git fetch','no git remote','no direct merge','no automatic pr creation','draft pr creation requires a future explicit policy pr']:
        assert s in text
