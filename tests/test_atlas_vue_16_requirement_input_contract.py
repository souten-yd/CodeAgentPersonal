from pathlib import Path


def test_requirement_input_component_exists() -> None:
    text = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8')
    for marker in [
        'Requirement',
        'Project path',
        'Start Atlas',
        'Planning settings',
        'createPlanPool',
        'Execution controls are intentionally unavailable in VUE16',
    ]:
        assert marker in text

    assert '<StatusCard title="Start Atlas">' in text
    assert 'What should Atlas build or fix?' not in text
    assert 'Create Plan' not in text


def test_plan_review_panel_shows_read_only_planpool_item_summary() -> None:
    text = Path('web/atlas-next/src/components/PlanReviewPanel.vue').read_text(encoding='utf-8')
    for marker in [
        'Read-only PlanPool item summary',
        'PlanPool item summary',
        'planPoolItems',
        'rawPlanPoolItems',
        'planpool-grid',
        'status={{ item.status }}',
        'phase={{ item.phase }}',
        'risk={{ item.risk }}',
        'type={{ item.type }}',
        'Review/clarify only',
    ]:
        assert marker in text

    lowered = text.lower()
    for forbidden in ['approve(', 'dryrun(', 'execute(', 'safeapply', 'rollback(', 'retry(', '@click', 'fetch(']:
        assert forbidden not in lowered


def test_vue_start_surface_has_single_primary_start_entrypoint() -> None:
    req = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8')
    shell = Path('web/atlas-next/src/components/WorkflowShell.vue').read_text(encoding='utf-8')
    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')
    combined = app + '\n' + req + '\n' + shell

    assert 'Start Atlas, then review the plan.' in app
    assert req.count('Start Atlas') >= 1
    assert 'Create Plan' not in combined
    assert '<button' not in shell
    assert 'Primary CTA' not in shell
    assert 'Start Atlas is the single Vue entry point' in shell
