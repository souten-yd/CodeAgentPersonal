import json
from pathlib import Path


def test_autonomous_execution_manifest_policy_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['autonomous_execution_readiness_policy']
    assert m['autonomous_execution_runtime_level'] == 'level_0_manual_only'
    assert m['autonomous_execution_enabled'] is False
    assert m['auto_continue_enabled'] is False
    assert m['execute_all_enabled'] is False
    assert m['automatic_safe_apply_enabled'] is False
    assert m['automatic_verification_enabled'] is False
    assert m['automatic_retry_enabled'] is False
    assert m['automatic_rollback_enabled'] is False

    for gate in [
        'snapshot_restore','patch_transaction','risk_classification','verification_allowlist','dry_run_and_approval',
        'rollback_readiness','artifact_capture','stop_kill_switch','loop_bounds','remote_git_restrictions','self_improvement_gate'
    ]:
        assert gate in m['autonomous_readiness_gates']

    assert m['final_goal'] == 'fully_autonomous_code_agent'
    assert m['self_improvement_scope'] == 'self_improving_codeagentpersonal_kasanecore'
    assert m['workflow_state_owner'] == 'backend'
    assert m['primary_cta_policy'] == 'single_existing_manual_action_only'
    for banned in ['build_queue','preview_token','advance_to_confirmation','execute_and_refresh','safe_apply','auto_verification','patch_generation','retry','rollback']:
        assert banned in m['primary_cta_forbidden_actions']
    assert m['vue_migration_plan_doc']
    assert m['vue_migration_checkpoint'] == 'PR-ATLAS-SCALE-80'
    assert m['autonomous_first_ui_policy'] == 'docs/atlas_autonomous_first_ui_policy.md'


def test_snapshot_restore_runtime_flags() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['autonomous_execution_runtime_level'] == 'level_0_manual_only'
    assert m['automatic_rollback_enabled'] is False
    if 'snapshot_restore_auto_enabled' in m:
        assert m['snapshot_restore_auto_enabled'] is False
