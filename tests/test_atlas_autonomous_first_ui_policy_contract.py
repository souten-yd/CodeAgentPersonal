from pathlib import Path


def test_autonomous_first_ui_policy_contract() -> None:
    p = Path('docs/atlas_autonomous_first_ui_policy.md')
    assert p.exists()
    t = p.read_text(encoding='utf-8')
    for s in [
        'Autonomous Execution Readiness Boundary',
        'docs/atlas_autonomous_execution_readiness_policy.md',
        'Automation-first UI does not mean autonomous execution is enabled',
        'ThinUI may expose readiness state, but not execute automatically',
        'Primary CTA remains single manual action only',
        'Minimal UI must show safety state before any future autonomous mode is exposed',
        'Autonomous-first UI Policy',
        'Default Visible UI',
        'Hide by Default',
        'Remove or Deprecate',
        'Anti-divergence Rules',
        'minimal_workflow',
        'safety_always_visible',
        'advanced_execution',
        'diagnostics',
        'deprecated',
        'removed_after_migration',
        'UI is not the source of workflow truth',
        'Do not make UI compute execution eligibility',
        'workflow_state',
        'available_actions',
        'CLI/TUI',
    ]:
        assert s in t
