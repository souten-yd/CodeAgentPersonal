
import json
from pathlib import Path

def test_manifest_verification_allowlist_contract():
    m=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['verification_allowlist_foundation'] is True
    assert m['verification_allowlist_runtime_gate'] == 'metadata_only_manual_foundation'
    assert m['verification_allowlist_auto_execute_enabled'] is False
    assert m['automatic_verification_enabled'] is False
    assert m['automatic_command_execution_enabled'] is False
    assert m['verification_commands_advisory_only'] is True
    assert m['autonomous_execution_runtime_level'] == 'level_0_manual_only'
    assert m['autonomous_execution_enabled'] is False
    assert m['automatic_patch_generation_enabled'] is False
    assert m['automatic_patch_apply_enabled'] is False
    assert m['automatic_rollback_enabled'] is False
    assert m['automatic_safe_apply_enabled'] is False
    assert m['risk_classification_foundation'] is True
    assert m['patch_transaction_foundation'] is True
    assert m['primary_cta_policy'] == 'single_existing_manual_action_only'
    assert m['final_goal'] == 'fully_autonomous_code_agent'
    assert m['self_improvement_scope'] == 'self_improving_codeagentpersonal_kasanecore'
    assert m['vue_migration_checkpoint'] == 'PR-ATLAS-SCALE-80'
