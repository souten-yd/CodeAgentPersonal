import json

from agent.atlas_automation_profile_resolver import normalize_automation_profile
from app.atlas.workflow_state_contract import build_read_only_workflow_state


PROFILE_PRESETS = {
    "review_only": "review_only",
    "guarded_single_action": "single_action",
    "supervised_bounded_auto": "supervised_auto",
    "autonomous_dev_agent": "full_auto",
}


def _payload_for(profile: str, artifacts: dict | None = None) -> dict:
    return build_read_only_workflow_state(
        goal="g",
        project_path="p",
        phase="read_only_preview",
        status="ok",
        primary_cta_label="Read-only",
        available_actions=[{"id": "execute", "label": "Execute", "kind": "mutation"}],
        artifacts=artifacts or {},
        profile_resolution=normalize_automation_profile(preset_id=PROFILE_PRESETS[profile]),
    )


def test_all_profiles_preserve_read_only_invariants() -> None:
    for profile in PROFILE_PRESETS:
        payload = _payload_for(profile)
        assert payload["backend_workflow_state_authoritative"] is True
        assert payload["vue_source_of_truth"] is False
        assert payload["vue_execution_enabled"] is False
        assert payload["autonomous_execution_enabled"] is False
        assert payload["primary_cta"]["enabled"] is False
        assert payload["safety"]["mutation_endpoints_enabled"] is False
        assert payload["level1_disabled_backend_skeleton"]["mutation_performed"] is False
        assert payload["level1_disabled_backend_skeleton"]["execution_performed"] is False
        assert all(action["enabled"] is False and action["read_only"] is True for action in payload["available_actions"])
        review = payload["guarded_execution_review"]
        for key in (
            "callable_execution_route_enabled",
            "execution_enabled",
            "approval_action_enabled",
            "dry_run_action_enabled",
            "execute_action_enabled",
            "apply_action_enabled",
            "verify_action_enabled",
            "rollback_action_enabled",
            "retry_continue_action_enabled",
        ):
            assert review[key] is False


def test_output_has_no_stale_scale_or_not_callable_literals() -> None:
    payload = _payload_for(
        "autonomous_dev_agent",
        artifacts={"dry_run": True, "snapshot": True, "allowlist": True, "risk": True, "loop_bound": True},
    )
    encoded = json.dumps(payload, sort_keys=True)
    assert "SCALE-94" not in encoded
    assert "SCALE-96" not in encoded
    assert "not callable" not in encoded


def test_artifacts_change_gate_evidence_status() -> None:
    missing = _payload_for("guarded_single_action")
    ready = _payload_for("guarded_single_action", artifacts={"dry_run": True})

    missing_gates = {
        item["gate_id"]: item
        for item in missing["level1_disabled_backend_skeleton"]["gate_source_map"]
    }
    ready_gates = {
        item["gate_id"]: item
        for item in ready["level1_disabled_backend_skeleton"]["gate_source_map"]
    }

    assert missing_gates["dry_run_proof"]["current_status"] == "missing_evidence"
    assert ready_gates["dry_run_proof"]["current_status"] == "satisfied"
    assert ready_gates["dry_run_proof"]["evidence_available"] is True


def test_preview_runtime_level_reflects_active_profile() -> None:
    assert _payload_for("review_only")["preview_runtime_level"] == "level_0_review_only"
    assert _payload_for("guarded_single_action")["preview_runtime_level"] == "level_1_guarded_single_step"
    assert (
        _payload_for("supervised_bounded_auto")["preview_runtime_level"]
        == "level_2_to_level4_supervised_bounded_auto"
    )
    assert _payload_for("autonomous_dev_agent")["preview_runtime_level"] == "level_8_fully_autonomous_code_agent"
