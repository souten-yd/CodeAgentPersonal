import json
from pathlib import Path


def test_patch_transaction_manifest_contract() -> None:
    m = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    assert m["patch_transaction_foundation"] is True
    assert m["patch_transaction_runtime_gate"] == "metadata_only_manual_foundation"
    assert m["patch_transaction_apply_enabled"] is False
    assert m["automatic_patch_generation_enabled"] is False
    assert m["automatic_patch_apply_enabled"] is False
    assert m["rollback_metadata_foundation"] is True
    assert m["rollback_metadata_auto_restore_enabled"] is False
    assert m["automatic_rollback_enabled"] is False
    assert m["autonomous_execution_runtime_level"] == "level_0_manual_only"
    assert m["autonomous_execution_enabled"] is False
    assert m["snapshot_restore_foundation"] is True
    assert m["snapshot_restore_path_safety_hardened"] is True
    assert m["primary_cta_policy"] == "single_existing_manual_action_only"
    assert m["final_goal"] == "fully_autonomous_code_agent"
    assert m["self_improvement_scope"] == "self_improving_codeagentpersonal_kasanecore"
    assert m["vue_migration_checkpoint"]
