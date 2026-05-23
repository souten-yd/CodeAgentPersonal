from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def test_scale_99_scope_remains_display_only() -> None:
    for d in DOCS:
        text = Path(d).read_text(encoding='utf-8')
        assert 'SCALE-99 may add export/copy metadata or another display-only refinement, not execution enable.' in text


def test_execution_safety_contract_still_disabled() -> None:
    for d in DOCS:
        text = Path(d).read_text(encoding='utf-8')
        assert 'runtime remains level_0_manual_only' in text
        assert 'Level-1 execution remains disabled' in text
        assert 'Autonomous execution remains disabled' in text
        assert 'Vue execution capability remains none' in text
        assert 'backend workflow_state remains authoritative' in text
        assert 'execute-all remains forbidden' in text.lower() or 'Do not add execute-all' in text or 'No execute-all, no auto-continue, and no autonomous execution' in text
        assert 'auto-continue remains disabled' in text.lower() or 'No execute-all, no auto-continue, and no autonomous execution' in text
