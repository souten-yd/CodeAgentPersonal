from pathlib import Path


def test_workflow_review_board_is_mounted_in_main_column() -> None:
    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')
    assert "import WorkflowReviewBoard from './WorkflowReviewBoard.vue'" in app
    assert '<WorkflowReviewBoard :snapshot="snapshot" />' in app
    assert app.index('<ConversationWorkbench />') < app.index('<WorkflowReviewBoard :snapshot="snapshot" />') < app.index('<WorkflowShell :snapshot="snapshot" />')


def test_workflow_review_board_covers_review_approval_and_preview_without_actions() -> None:
    text = Path('web/atlas-next/src/components/WorkflowReviewBoard.vue').read_text(encoding='utf-8')
    for marker in [
        'Review Board',
        'Plan Review',
        'Approval Review',
        'Execute Preview',
        'Backend authority',
        'Vue does not approve, execute, apply, verify, rollback, retry, or continue',
    ]:
        assert marker in text

    for forbidden in ['<button', '@click', 'fetch(', 'createPlanPool', 'approve(', 'execute(', 'apply(']:
        assert forbidden not in text
