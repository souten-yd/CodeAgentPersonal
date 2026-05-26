from pathlib import Path


def test_guarded_execution_preparation_panel_is_mounted_after_patch_review() -> None:
    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')
    assert "import GuardedExecutionPreparationPanel from './GuardedExecutionPreparationPanel.vue'" in app
    assert '<GuardedExecutionPreparationPanel :review="snapshot.guardedExecutionReview" />' in app
    assert app.index('<PatchReviewPanel :snapshot="snapshot" />') < app.index('<GuardedExecutionPreparationPanel :review="snapshot.guardedExecutionReview" />')
    assert 'patchTransaction: {' in app


def test_guarded_execution_preparation_panel_stays_display_only() -> None:
    panel = Path('web/atlas-next/src/components/GuardedExecutionPreparationPanel.vue').read_text(encoding='utf-8')
    for needle in [
        'Guarded Execution Preparation (Display-only)',
        'review.reviewItems',
        'review.blockedReasons',
        'requiresDryRun',
        'requiresApproval',
        'Vue does not approve, dry-run, execute, apply, verify, rollback, retry, or continue actions.',
    ]:
        assert needle in panel
    lowered = panel.lower()
    for forbidden in ['@click', 'fetch(', 'approve(', 'execute(', 'safeapply', 'rollback(', 'retry(']:
        assert forbidden not in lowered
