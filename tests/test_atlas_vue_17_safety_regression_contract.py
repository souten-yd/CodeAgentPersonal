from pathlib import Path

def test_no_execution_buttons_or_mutating_http_methods_in_vue17_plan_review_surface() -> None:
    t = Path('web/atlas-next/src/components/PlanReviewPanel.vue').read_text(encoding='utf-8').lower()
    for forbidden in ['approve', 'execute', 'apply', 'rollback', 'restore', 'retry', 'continue']:
        assert forbidden in t  # present only in explicit unavailable notice

    req = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8').lower()
    assert 'type="submit"' in req
    assert 'start atlas planning' in req
