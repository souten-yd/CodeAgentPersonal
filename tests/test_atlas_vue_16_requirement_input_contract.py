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
