from pathlib import Path

DOCS = '\n'.join(
    Path(p).read_text()
    for p in [
        'docs/atlas_scale_master_roadmap.md',
        'docs/atlas_development_handoff.md',
        'docs/atlas_autonomous_execution_readiness_policy.md',
        'docs/atlas_thinui_readiness.md',
        'docs/atlas_vue_migration_plan.md',
    ]
)


def test_102b_safety_statements_present():
    for token in [
        'Level-1 execution remains disabled',
        'Runtime remains level_0_manual_only',
        'Autonomous execution remains disabled',
        'Vue execution capability remains none',
        'backend workflow_state remains authoritative',
    ]:
        assert token in DOCS
