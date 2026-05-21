from pathlib import Path


def test_state_machine_tokens_and_iife_binding():
    js = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    for token in [
        'deriveWorkflowPhase', 'handleWorkflowPrimaryAction', 'primary_action_kind',
        'primary_action_enabled', 'primary_action_reason', 'workflow_phase',
        'auto_continue_allowed', 'execute_all_allowed', 'confirmation_text_required',
        'EXECUTE ONE ACTION'
    ]:
        assert token in js
    end = js.rfind('})();')
    assert js.find('handleWorkflowPrimaryAction', 0, end) != -1
    assert js.find("atlas-workflow-primary-action-btn')?.addEventListener", 0, end) != -1
    assert js.find("atlas-workflow-primary-action-btn')?.addEventListener", end) == -1
    assert 'safe_apply' not in js[js.find('function handleWorkflowPrimaryAction'):js.find('function bindWorkflowShell')].lower()
    for banned in ['patch generation', 'rollback', 'automatic verification', 'execute all', 'auto continue']:
        assert banned not in js[js.find('function handleWorkflowPrimaryAction'):js.find('function bindWorkflowShell')].lower()
    assert 'operatorLoopCanExecute()' in js
    assert 'import ' not in js and 'export ' not in js


def test_primary_cta_uses_operator_loop_guards():
    js = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'function getOperatorLoopGuardState' in js
    derive = js[js.index('function deriveWorkflowPhase'):js.index('function getAtlasUiMode')]
    assert 'getOperatorLoopGuardState()' in derive
    assert 'enabled: guardState.canPrepare' in derive
    assert "if (guardState.canDryRun)" in derive
    assert "if (guardState.canExecute)" in derive or 'operatorLoopCanExecute()' in derive
    handler = js[js.index('function handleWorkflowPrimaryAction'):js.index('function bindWorkflowShell')]
    for banned in ['operatorLoopBuildQueue', 'operatorLoopToken', 'operatorLoopAdvanceToConfirmation', 'operatorLoopExecuteAndRefresh']:
        assert banned not in handler
