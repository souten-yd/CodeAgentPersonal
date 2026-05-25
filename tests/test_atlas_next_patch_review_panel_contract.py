from pathlib import Path


def test_patch_review_panel_is_mounted_after_review_board() -> None:
    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')
    assert "import PatchReviewPanel from './PatchReviewPanel.vue'" in app
    assert '<PatchReviewPanel :snapshot="snapshot" />' in app
    assert app.index('<WorkflowReviewBoard :snapshot="snapshot" />') < app.index('<PatchReviewPanel :snapshot="snapshot" />') < app.index('<WorkflowShell :snapshot="snapshot" />')


def test_patch_review_panel_is_display_only_and_no_apply_path() -> None:
    text = Path('web/atlas-next/src/components/PatchReviewPanel.vue').read_text(encoding='utf-8')
    for marker in [
        'Patch Review (Display-only)',
        'Patch candidate',
        'Apply readiness',
        'Verification evidence',
        'Rollback evidence',
        'Vue does not generate, approve, apply, verify, rollback, retry, or continue patches',
    ]:
        assert marker in text

    for forbidden in ['<button', '@click', 'fetch(', 'createPlanPool', 'approve(', 'execute(', 'apply(', 'safeApply']:
        assert forbidden not in text
