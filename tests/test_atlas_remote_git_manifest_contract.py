import json
from pathlib import Path

def test_remote_git_manifest_contract():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['remote_git_gate_foundation'] is True
    assert m['remote_git_runtime_gate'] == 'metadata_only_manual_foundation'
    for k in ['remote_git_operations_enabled','git_push_enabled','git_pull_enabled','git_clone_enabled','git_fetch_enabled','git_remote_enabled','branch_creation_enabled','automatic_pr_creation_enabled','draft_pr_creation_enabled','direct_merge_enabled','remote_git_gate_auto_execute_enabled','bounded_loop_runtime_enabled','automatic_loop_enabled','automatic_retry_enabled','auto_continue_enabled','execute_all_enabled','automatic_execute_enabled','automatic_command_execution_enabled','automatic_safe_apply_enabled','automatic_patch_generation_enabled','automatic_patch_apply_enabled','automatic_restore_enabled','automatic_rollback_enabled','autonomous_execution_enabled']:
        assert m[k] is False
    assert m['loop_bound_gate_foundation'] is True
    assert m['stop_kill_switch_gate_foundation'] is True
    assert m['artifact_capture_gate_foundation'] is True
    assert m['rollback_readiness_gate_foundation'] is True
    assert m['dry_run_approval_gate_foundation'] is True
    assert m['verification_allowlist_foundation'] is True
    assert m['risk_classification_foundation'] is True
    assert m['patch_transaction_foundation'] is True
    assert m['snapshot_restore_foundation'] is True
    assert m['autonomous_execution_runtime_level'] == 'level_0_manual_only'
    assert m['primary_cta_policy'] == 'single_existing_manual_action_only'
    assert m['final_goal'] == 'fully_autonomous_code_agent'
    assert m['self_improvement_scope'] == 'self_improving_codeagentpersonal_kasanecore'
    assert 'vue' in json.dumps(m).lower()
