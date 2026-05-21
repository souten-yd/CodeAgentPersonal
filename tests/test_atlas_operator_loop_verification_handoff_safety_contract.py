from pathlib import Path

def test_no_forbidden_execution_tokens_in_changed_paths():
    files = [
        Path('web/js/atlas_dashboard.js'),
        Path('agent/atlas_next_action_orchestrator_service.py'),
        Path('ui.html'),
        Path('tests/test_atlas_operator_loop_verification_handoff_copy_export_ui_contract.py'),
    ]
    text = '\n'.join(p.read_text(encoding='utf-8') for p in files)
    for token in ['shell=True', 'subprocess.run', 'git push', 'git pull', 'git clone', 'Path("ca_data")']:
        assert token not in text

def test_copy_export_path_is_display_only():
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    s = dash.index('function buildOperatorLoopVerificationHandoffExportPayload')
    e = dash.index('function operatorLoopRender')
    section = dash[s:e]
    for forbidden in ['runVerification', 'autoVerifyOne', 'safe_apply', 'patch generation', 'retry', 'rollback', 'executeManualNextAction']:
        assert forbidden not in section
