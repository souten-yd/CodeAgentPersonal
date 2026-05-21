from pathlib import Path

def test_copy_export_controls_and_runtime_wiring_contract():
    ui = Path('ui.html').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    card = ui.index('atlas-operator-loop-card')
    summary = ui.index('atlas-operator-loop-verification-handoff-summary')
    result = ui.index('atlas-operator-loop-verification-handoff-result')
    copy_btn = ui.index('atlas-operator-loop-verification-handoff-copy-btn')
    export_btn = ui.index('atlas-operator-loop-verification-handoff-export-btn')
    status = ui.index('atlas-operator-loop-verification-handoff-copy-status')
    assert card < summary < result < copy_btn < export_btn < status
    assert '<pre id="atlas-operator-loop-verification-handoff-copy-btn"' not in ui
    assert 'Copy Verification Handoff' in ui and 'Export Verification Handoff JSON' in ui
    snippet = ui[summary:status+300]
    for bad in ['Execute Verification Handoff', 'Run verification handoff', 'Retry handoff', 'Rollback handoff']:
        assert bad not in snippet
    for fn in ['buildOperatorLoopVerificationHandoffExportPayload', 'copyOperatorLoopVerificationHandoff', 'exportOperatorLoopVerificationHandoff']:
        assert fn in dash
    assert 'confirmation_text_required' in dash and 'EXECUTE ONE ACTION' in dash and 'dry_run_first_required' in dash
    assert 'navigator?.clipboard?.writeText' in dash
    assert 'new Blob' in dash and 'URL.createObjectURL' in dash
    assert "$('atlas-operator-loop-verification-handoff-copy-btn')?.addEventListener('click',copyOperatorLoopVerificationHandoff);" in dash
    assert "$('atlas-operator-loop-verification-handoff-export-btn')?.addEventListener('click',exportOperatorLoopVerificationHandoff);" in dash
    final = dash.rfind('})();')
    assert dash.index('copyOperatorLoopVerificationHandoff') < final
    assert dash.index('exportOperatorLoopVerificationHandoff') < final
    assert 'type="module"' not in ui
    assert 'import ' not in dash and 'export ' not in dash
    assert 'atlas-dashboard-40' in ui
