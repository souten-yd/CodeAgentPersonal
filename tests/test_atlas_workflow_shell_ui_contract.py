from pathlib import Path


def test_workflow_shell_dom_and_safety():
    html=Path('ui.html').read_text(encoding='utf-8')
    for sid in [
      'atlas-workflow-shell','atlas-workflow-goal','atlas-workflow-project-path','atlas-workflow-mode','atlas-workflow-status','atlas-workflow-phase','atlas-workflow-primary-action-btn','atlas-workflow-primary-action-reason','atlas-workflow-safety-summary','atlas-workflow-stop-btn','atlas-workflow-approval-summary','atlas-workflow-artifacts-summary','atlas-workflow-advanced-toggle','atlas-workflow-diagnostics-toggle'
    ]:
      assert f'id="{sid}"' in html
    shell = html[html.index('id="atlas-workflow-shell"'):html.index('id="atlas-goal-title"')]
    for bad in ['execute all','auto continue','automatic verification','safe_apply','patch generation']:
      assert bad not in shell.lower()
    assert 'atlas-dashboard-42' in html
    assert 'type="module"' not in html


def test_workflow_shell_js_contract():
    js=Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    for token in ['state.workflowShell','getWorkflowShellState','deriveWorkflowPhase','handleWorkflowPrimaryAction','renderWorkflowShell','bindWorkflowShell']:
      assert token in js
    assert 'import ' not in js and 'export ' not in js
    end=js.rfind('})();')
    assert js.find('bindWorkflowShell',0,end) != -1
    assert js.find('bindWorkflowShell',end) == -1
