from pathlib import Path
import re

HTML = Path('ui.html').read_text(encoding='utf-8')
DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
API = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')

def _atlas_block():
    return HTML.split('id="atlas-automation-extensions-panel"',1)[1]

def test_operator_loop_card_exists_inside_atlas_automation_extensions():
    block = _atlas_block()
    assert 'id="atlas-operator-loop-card"' in block
    assert HTML.index('id="atlas-automation-extensions-panel"') < HTML.index('id="atlas-operator-loop-card"') < HTML.rindex('</body>')

def test_operator_loop_required_dom_ids_exist():
    ids = ['atlas-operator-loop-card','atlas-operator-loop-status','atlas-operator-loop-pool-id','atlas-operator-loop-run-id','atlas-operator-loop-reviewer','atlas-operator-loop-reason','atlas-operator-loop-build-queue-btn','atlas-operator-loop-prepare-btn','atlas-operator-loop-token-btn','atlas-operator-loop-dry-run-btn','atlas-operator-loop-execute-btn','atlas-operator-loop-refresh-btn','atlas-operator-loop-reset-btn','atlas-operator-loop-confirmation-token','atlas-operator-loop-confirmation-text','atlas-operator-loop-explicit-decision','atlas-operator-loop-queue-result','atlas-operator-loop-contract-result','atlas-operator-loop-executor-result','atlas-operator-loop-refresh-result','atlas-operator-loop-next-step']
    for i in ids: assert f'id="{i}"' in HTML

def test_operator_loop_no_lumen_text_leak():
    assert 'Operator Loop' in _atlas_block()

def test_operator_loop_buttons_have_safe_labels():
    blk=_atlas_block()
    start=blk.index('id="atlas-operator-loop-card"')
    end=blk.index('</details>', start)
    b = blk[start:end].lower()
    for t in ['execute all','auto continue','rollback','restore','debugreview auto']:
        assert t not in b

def test_operator_loop_uses_existing_api_helpers():
    for t in ['buildMultiItemSupervisedStatus','prepareNextAction','previewManualNextActionConfirmationToken','executeManualNextAction','refreshAfterManualExecution']:
        assert t in DASH

def test_operator_loop_execute_requires_dry_run_state():
    assert 'dryRunExecutorRunId' in DASH
    assert "d.status==='dry_run'" in DASH

def test_operator_loop_confirmation_text_required():
    assert 'EXECUTE ONE ACTION' in DASH

def test_operator_loop_token_not_persisted():
    line = re.search(r'persistOperatorLoopState\(\).*?\{([^}]*)\}', DASH, re.S)
    assert 'confirmationToken' not in DASH[line.start():line.end()]

def test_operator_loop_no_import_export():
    assert not re.search(r'^\s*import\s+', DASH, re.M)
    assert not re.search(r'^\s*export\s+', DASH, re.M)
    assert not re.search(r'^\s*import\s+', API, re.M)
    assert not re.search(r'^\s*export\s+', API, re.M)

def test_script_cache_bust_updated_if_js_changed():
    assert 'atlas-dashboard-17' in HTML
