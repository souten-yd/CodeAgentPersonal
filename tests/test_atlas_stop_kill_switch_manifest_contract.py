import json
from pathlib import Path


def test_stop_manifest_fields() -> None:
    m = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    assert m["stop_kill_switch_gate_foundation"] is True
    assert m["stop_kill_switch_runtime_gate"] == "metadata_only_manual_foundation"
    assert m["stop_kill_switch_auto_execute_enabled"] is False
    assert m["automatic_stop_execution_enabled"] is False
    assert m["stop_state_visibility_required"] is True
    assert m["kill_switch_required"] is True
    assert m["auto_continue_enabled"] is False
    assert m["execute_all_enabled"] is False
    assert m["automatic_retry_enabled"] is False
    assert m["automatic_execute_enabled"] is False
    assert m["automatic_dry_run_enabled"] is False
    assert m["automatic_approval_enabled"] is False
    assert m["automatic_artifact_capture_enabled"] is False
    assert m["automatic_verification_enabled"] is False
    assert m["automatic_command_execution_enabled"] is False
    assert m["automatic_safe_apply_enabled"] is False
    assert m["automatic_patch_generation_enabled"] is False
    assert m["automatic_patch_apply_enabled"] is False
    assert m["automatic_restore_enabled"] is False
    assert m["automatic_rollback_enabled"] is False
    assert m["autonomous_execution_runtime_level"] == "level_0_manual_only"
    assert m["autonomous_execution_enabled"] is False
    assert m["artifact_capture_gate_foundation"] is True
    assert m["rollback_readiness_gate_foundation"] is True
    assert m["dry_run_approval_gate_foundation"] is True
    assert m["verification_allowlist_foundation"] is True
    assert m["risk_classification_foundation"] is True
    assert m["patch_transaction_foundation"] is True
    assert m["snapshot_restore_foundation"] is True
    assert m["primary_cta_policy"] == "single_existing_manual_action_only"
    assert m["final_goal"] == "fully_autonomous_code_agent"
    assert m["self_improvement_scope"] == "self_improving_codeagentpersonal_kasanecore"
    assert m["vue_migration_checkpoint"] == "PR-ATLAS-SCALE-80"
