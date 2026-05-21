from pathlib import Path


def test_autonomous_first_ui_policy_contract() -> None:
    p = Path('docs/atlas_autonomous_first_ui_policy.md')
    assert p.exists()
    t = p.read_text(encoding='utf-8')
    for s in [
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
