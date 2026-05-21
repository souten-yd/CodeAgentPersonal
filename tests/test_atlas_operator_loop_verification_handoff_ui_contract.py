from pathlib import Path


def test_operator_loop_handoff_ui_contract():
    ui = Path('ui.html').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    final = dash.rfind('})();')
    assert 'atlas-operator-loop-verification-handoff-summary' in ui
    assert 'atlas-operator-loop-verification-handoff-result' in ui
    assert ui.index('atlas-operator-loop-card') < ui.index('atlas-operator-loop-verification-handoff-summary') < ui.index('atlas-operator-loop-verification-handoff-result')
    assert '<pre id="atlas-operator-loop-verification-handoff-summary"' not in ui
    assert 'getOperatorLoopVerificationHandoff' in dash
    assert 'renderOperatorLoopVerificationHandoff' in dash
    assert 'operatorLoopState.lastContractResult?.action_contract?.metadata?.verification_recommendation_handoff' in dash
    assert 'approval_summary' in dash and 'manual_approval_only' in dash and 'executed' in dash
    assert dash.index('renderOperatorLoopVerificationHandoff();') > dash.index('function operatorLoopRender(')
    assert dash.index('getOperatorLoopVerificationHandoff') < final
    assert dash.index('renderOperatorLoopVerificationHandoff') < final
    assert 'type="module"' not in ui
    assert 'import ' not in dash and 'export ' not in dash
    assert 'atlas-dashboard-39' in ui
    assert 'EXECUTE ONE ACTION' in ui and 'EXECUTE ONE ACTION' in dash
    for bad in ['Run verification', 'safe_apply', 'retry', 'rollback']:
        assert bad not in ui[ui.index('atlas-operator-loop-card'):ui.index('atlas-operator-loop-card')+3000]


def test_handoff_summary_includes_manual_only_note_and_execution_requirement_unchanged():
    ui = Path('ui.html').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert "Manual approval context only. Suggested commands were not executed." in dash
    assert "executed" in dash
    assert "EXECUTE ONE ACTION" in ui and "EXECUTE ONE ACTION" in dash
