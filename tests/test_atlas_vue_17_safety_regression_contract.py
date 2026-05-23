from pathlib import Path


def test_plan_review_panel_is_display_only_and_has_no_actions_or_api_calls() -> None:
    text = Path('web/atlas-next/src/components/PlanReviewPanel.vue').read_text(encoding='utf-8').lower()

    assert '<button' not in text
    assert '@click' not in text
    assert 'submit' not in text
    assert "import { createplanpool" not in text
    assert "import { fetch" not in text
    assert 'fetch(' not in text




def test_requirement_input_only_has_planning_submit_and_only_calls_create_plan_pool() -> None:
    text = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8')
    lower = text.lower()

    assert lower.count('<button') == 1
    assert 'type="submit"' in text
    assert '@submit.prevent="submitPlanning"' in text
    assert 'createPlanPool' in text
    assert lower.count('createplanpool') >= 2

    forbidden_button_words = ['approve', 'execution', 'execute', 'apply', 'dry-run', 'dry run', 'verify', 'rollback', 'restore', 'retry', 'continue']
    for word in forbidden_button_words:
        assert f'>{word}<' not in lower
