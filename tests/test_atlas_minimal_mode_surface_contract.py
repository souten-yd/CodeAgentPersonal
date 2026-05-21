from pathlib import Path


def _window(html: str, sid: str, radius: int = 320):
    idx = html.index(f'id="{sid}"')
    return html[max(0, idx - radius): idx + radius]


def test_minimal_mode_default_and_css_visibility_contract():
    html = Path("ui.html").read_text(encoding="utf-8")
    assert 'id="atlas-dashboard"' in html
    assert 'data-atlas-ui-mode="minimal"' in html
    assert '#atlas-dashboard[data-atlas-ui-mode="minimal"] .atlas-surface-advanced' in html
    assert '#atlas-dashboard[data-atlas-ui-mode="minimal"] .atlas-surface-diagnostics' in html


def test_minimal_and_safety_surfaces_visible_and_classified():
    html = Path("ui.html").read_text(encoding="utf-8")
    assert 'id="atlas-workflow-shell" class="atlas-panel-card atlas-surface-minimal"' in html
    for sid in [
        'atlas-workflow-primary-action-btn',
        'atlas-workflow-primary-action-reason',
        'atlas-workflow-safety-summary',
        'atlas-workflow-stop-btn',
    ]:
        assert f'id="{sid}"' in html


def test_advanced_and_diagnostics_surfaces_hidden_but_dom_present():
    html = Path("ui.html").read_text(encoding="utf-8")
    for sid in [
        'atlas-diagnostics-drawer',
        'atlas-automation-readiness-panel',
        'atlas-operator-loop-card',
        'atlas-diagnostics-raw-json-section',
    ]:
        assert f'id="{sid}"' in html

    assert 'id="atlas-diagnostics-drawer" class="atlas-panel-card atlas-surface-diagnostics"' in html
    assert 'id="atlas-automation-readiness-panel" class="atlas-panel-card atlas-surface-advanced"' in html


def test_minimal_workflow_shell_does_not_expose_forbidden_controls():
    html = Path("ui.html").read_text(encoding="utf-8").lower()
    shell = html[html.index('id="atlas-workflow-shell"'):html.index('id="atlas-goal-title"')]
    for forbidden in [
        'build queue',
        'preview token',
        'advance to confirmation',
        'execute and refresh',
        'auto verification',
        'auto safe_apply',
        'raw json',
        'repo index',
        'repo context',
        'planner packaging',
        'context refresh',
        'verification recommendation',
        'patch generation',
        'retry',
        'rollback',
    ]:
        assert forbidden not in shell
