from pathlib import Path


def test_scale_93_level1_design_boundary_markers_present() -> None:
    text = Path('docs/atlas_autonomous_execution_readiness_policy.md').read_text(encoding='utf-8')
    required = [
        'PR-ATLAS-SCALE-93 Level-1 Guarded Execution Design Checkpoint',
        'SCALE-93 is a design-only checkpoint',
        'Guarded single-step execution candidate only',
        'Exactly one action at a time',
        'Low-risk only',
        'Dry-run-first is mandatory',
        'Explicit human approval token is mandatory',
        'Backend-owned execution authority only',
        'Vue has no execution authority',
        'No auto-continue',
        'No execute-all',
        'No autonomous loop',
        'No remote git push/merge',
        'No self-modification execution',
        'No Level-2 behavior',
    ]
    for marker in required:
        assert marker in text
