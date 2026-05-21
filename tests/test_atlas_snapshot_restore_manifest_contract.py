import json
from pathlib import Path


def test_snapshot_restore_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['snapshot_restore_foundation'] is True
    assert m['snapshot_restore_runtime_gate'] == 'manual_only_foundation'
    assert m['snapshot_restore_path_safety_hardened'] is True
    assert m['snapshot_restore_symlink_policy'] == 'skip'
    assert m['snapshot_restore_delete_missing_before'] == 'plan_only_non_destructive'
    assert m['snapshot_restore_auto_enabled'] is False
    assert m['automatic_rollback_enabled'] is False
    assert m['autonomous_execution_runtime_level'] == 'level_0_manual_only'
    assert m['autonomous_execution_enabled'] is False
    assert m['primary_cta_policy'] == 'single_existing_manual_action_only'
    assert m['self_improvement_scope'] == 'self_improving_codeagentpersonal_kasanecore'
    assert m['vue_migration_checkpoint'] == 'PR-ATLAS-SCALE-80'
