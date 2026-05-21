import json
from pathlib import Path

def test_manifest_contract():
    m=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['self_improvement_gate_foundation'] is True
    assert m['self_improvement_runtime_gate']=='metadata_only_manual_foundation'
    assert m['self_improvement_scope']=='self_improving_codeagentpersonal_kasanecore'
    assert m['self_improvement_strict_gate_required'] is True
    assert m['self_improvement_auto_execute_enabled'] is False
    assert m['autonomous_self_improvement_enabled'] is False
    assert m['automatic_self_modification_enabled'] is False
    assert m['self_modification_strict_gate_required'] is True
    assert m['self_modification_auto_apply_enabled'] is False

    assert m['self_improvement_policy']=='docs/atlas_self_development_rules.md'
    assert m['self_improvement_readiness_policy']=='docs/atlas_autonomous_execution_readiness_policy.md#self-improvement-gate'
    assert m['automatic_command_execution_enabled'] is False
    assert m['automatic_patch_generation_enabled'] is False
    assert m['automatic_patch_apply_enabled'] is False
    assert m['automatic_safe_apply_enabled'] is False
    assert m['automatic_restore_enabled'] is False
    assert m['automatic_rollback_enabled'] is False
    assert m['bounded_loop_runtime_enabled'] is False
    assert m['remote_git_gate_foundation'] is True
    assert m['remote_git_operations_enabled'] is False
    assert m['automatic_pr_creation_enabled'] is False
    assert m['direct_merge_enabled'] is False
    assert m['loop_bound_gate_foundation'] is True
    assert m['automatic_loop_enabled'] is False
    assert m['automatic_retry_enabled'] is False
    assert m['auto_continue_enabled'] is False
    assert m['execute_all_enabled'] is False
    assert m['autonomous_execution_runtime_level']=='level_0_manual_only'
    assert m['primary_cta_policy']=='single_existing_manual_action_only'
    assert m['final_goal']=='fully_autonomous_code_agent'
    assert m['vue_migration_checkpoint']=='PR-ATLAS-SCALE-80'
