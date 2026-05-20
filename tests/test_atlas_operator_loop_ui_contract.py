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
    ids = ['atlas-operator-loop-card','atlas-operator-loop-status','atlas-operator-loop-pool-id','atlas-operator-loop-run-id','atlas-operator-loop-reviewer','atlas-operator-loop-reason','atlas-operator-loop-build-queue-btn','atlas-operator-loop-prepare-btn','atlas-operator-loop-token-btn','atlas-operator-loop-dry-run-btn','atlas-operator-loop-execute-btn','atlas-operator-loop-refresh-btn','atlas-operator-loop-reset-btn','atlas-operator-loop-copy-payload-btn','atlas-operator-loop-confirmation-token','atlas-operator-loop-confirmation-text','atlas-operator-loop-explicit-decision','atlas-operator-loop-disabled-reason','atlas-operator-loop-current-step','atlas-operator-loop-next-action-summary','atlas-operator-loop-diagnostics','atlas-operator-loop-queue-result','atlas-operator-loop-contract-result','atlas-operator-loop-executor-result','atlas-operator-loop-refresh-result','atlas-operator-loop-next-step']
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

def test_operator_loop_refresh_updates_next_action_state():
    for key in ['next_action_orchestrator_result','selected_item_id','selected_next_action','action_contract?.action_id','action_contract?.action_kind','Next action prepared. Dry run required.']:
        assert key in DASH

def test_operator_loop_buttons_have_disabled_reason_dom():
    for text in ['Build Queue requires pool_id.','Prepare requires multi_status_run_id.','Preview Token requires action_ready contract.','Dry Run requires confirmation token and payload_valid=true.','Execute requires successful dry_run.','Refresh requires executor_run_id.']:
        assert text in DASH or text in HTML

def test_operator_loop_render_updates_button_disabled_states():
    for key in ['build-queue-btn','prepare-btn','token-btn','dry-run-btn','execute-btn','refresh-btn']:
        assert key in DASH
    assert 'actionKind===\'execution_candidate\'' in DASH

def test_operator_loop_execute_disabled_without_successful_dry_run():
    assert "d.validation&&d.validation.executable===true" in DASH

def test_operator_loop_refresh_clears_previous_confirmation_and_executor_state():
    for key in ["operatorLoopState.confirmationToken='';","operatorLoopState.dryRunExecutorRunId='';","operatorLoopState.executedExecutorRunId='';","operatorLoopState.lastDryRunResult=null;","operatorLoopState.lastExecuteResult=null;"]:
        assert key in DASH

def test_operator_loop_explicit_decision_only_for_approval():
    assert "selectedNextAction==='approve_patch_candidate'" in DASH
    assert "operatorLoopState.explicitDecision==='approve'" in DASH

def test_operator_loop_copy_payload_excludes_token():
    assert 'atlas-operator-loop-copy-payload-btn' in HTML
    assert 'action_contract?.payload' in DASH
    assert 'atlas-operator-loop-diagnostics' in DASH

def test_operator_loop_local_storage_safe_subset():
    assert 'selectedItemId' in DASH and 'selectedNextAction' in DASH and 'actionKind' in DASH
    assert 'dryRunExecutorRunId:operatorLoopState.dryRunExecutorRunId' not in DASH

def test_operator_loop_smoke_mocks_exist():
    smoke = Path('scripts/smoke_ui_modes_playwright.py').read_text(encoding='utf-8')
    for endpoint in ['/api/atlas/multi-item-supervised-status/build','/api/atlas/next-action-orchestrator/prepare','/api/atlas/manual-next-action-executor/confirmation-token-preview','/api/atlas/manual-next-action-executor/execute','/api/atlas/post-manual-execution-refresh/refresh']:
        assert endpoint in smoke

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
    assert 'atlas-dashboard-24' in HTML
