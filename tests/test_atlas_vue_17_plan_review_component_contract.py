from pathlib import Path

def test_plan_review_component_exists_and_read_only_review_fields_present() -> None:
    text = Path('web/atlas-next/src/components/PlanReviewPanel.vue').read_text(encoding='utf-8')
    for marker in [
        'Atlas Plan Review (Read-only)', 'Planner questions', 'Clarification session',
        'Requirement summary', 'Plan summary', 'PlanPool item metadata',
        'Review/clarify only', 'approval', 'dry-run', 'execute', 'apply', 'rollback', 'continue'
    ]:
        assert marker in text


def test_requirement_input_uses_plan_review_panel() -> None:
    text = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8')
    assert 'PlanReviewPanel' in text
    assert '<PlanReviewPanel' in text
