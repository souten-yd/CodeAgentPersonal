from pathlib import Path


def test_primary_cta_surface_and_safety_text():
    html = Path('ui.html').read_text(encoding='utf-8')
    for sid in ['atlas-workflow-primary-action-btn','atlas-workflow-primary-action-reason','atlas-workflow-safety-summary']:
        assert f'id="{sid}"' in html
    shell = html[html.index('id="atlas-workflow-shell"'):html.index('id="atlas-goal-title"')]
    for phrase in ['dry-run-first', 'EXECUTE ONE ACTION', 'no auto-continue', 'no execute-all']:
        assert phrase in shell
    for bad in ['execute-all-btn', 'auto-continue-btn', 'safe-apply-btn', 'retry', 'rollback', 'patch generation']:
        assert bad not in shell.lower()
