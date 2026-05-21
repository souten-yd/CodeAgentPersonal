from pathlib import Path
import re


def _body(js: str, fn: str) -> str:
    m = re.search(rf"function\s+{fn}\s*\([^)]*\)\s*\{{", js)
    assert m, f"{fn} missing"
    i = m.end()
    depth = 1
    while i < len(js) and depth:
        if js[i] == '{':
            depth += 1
        elif js[i] == '}':
            depth -= 1
        i += 1
    return js[m.start():i]


def test_primary_cta_guard_alignment_contract():
    js = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    guard = _body(js, 'getOperatorLoopGuardState')
    derive = _body(js, 'deriveWorkflowPhase')
    handler = _body(js, 'handleWorkflowPrimaryAction')
    assert 'deriveWorkflowPhase(shellState)' in js and 'getOperatorLoopGuardState()' in derive
    for token in ['canPrepare','canPreviewToken','canDryRun','canExecute','canRefresh','confirmationOk','payloadValid','explicitDecisionOk','dryRunReady']:
        assert token in guard
    assert 'canPrepare=hasPoolId&&hasMultiStatusRunId' in guard.replace(' ','')
    for token in ['hasConfirmationToken','confirmationTextOk','EXECUTE ONE ACTION','payloadValid','isExecutionCandidate']:
        assert token in guard
    assert "if (guardState.canExecute)" in derive and 'actionKind: \'execute_one\'' in derive and 'operatorLoopCanExecute()' in guard
    assert 'enabled: guardState.canPrepare' in derive
    assert 'if (guardState.canDryRun)' in derive and "actionKind: 'dry_run'" in derive
    for banned in ['operatorLoopBuildQueue','operatorLoopToken','operatorLoopAdvanceToConfirmation','operatorLoopExecuteAndRefresh','safe_apply','verification recommendation','patch generation','retry','rollback']:
        assert banned.lower() not in handler.lower()
    for case in re.findall(r'case\s+\'[^\']+\':[\s\S]*?break;', handler):
        assert case.count('await ') <= 1
