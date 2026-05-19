from pathlib import Path
HTML=Path('ui.html').read_text(encoding='utf-8')
DASH=Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
API=Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')

def test_guarded_loop_buttons_exist():
    for i in ['atlas-operator-loop-advance-btn','atlas-operator-loop-execute-refresh-btn','atlas-operator-loop-semi-auto-status','atlas-operator-loop-guarded-result']:
        assert f'id="{i}"' in HTML

def test_guarded_loop_uses_api_helper():
    assert 'runGuardedOperatorLoop' in API

def test_guarded_loop_no_execute_all_auto_continue_labels():
    assert 'Execute all' not in HTML and 'Auto continue' not in HTML

def test_guarded_loop_token_not_persisted():
    assert 'confirmationToken' not in DASH[DASH.find('persistOperatorLoopState'):DASH.find('loadOperatorLoopState')]

def test_guarded_loop_cache_bust_18(): assert 'atlas-dashboard-18' in HTML
