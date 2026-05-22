from pathlib import Path


def test_requirement_input_component_exists() -> None:
    text = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8')
    for marker in [
        'Requirement / goal',
        'Project path',
        'Start Atlas Planning',
        'createPlanPool',
        'Execution controls are intentionally unavailable in VUE16',
    ]:
        assert marker in text
