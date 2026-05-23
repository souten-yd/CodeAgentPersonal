from app.atlas.level1_guarded_execution import Level1GuardedExecutionSkeleton


def test_scale_94_level1_disabled_skeleton_contract() -> None:
    payload = Level1GuardedExecutionSkeleton.build_disabled_level1_contract()
    assert payload["enabled"] is False
    assert payload["runtime_level"] == "level_0_manual_only"
    assert payload["level1_execution_enabled"] is False
    assert payload["backend_skeleton_enabled"] is True
    assert payload["callable_execution_endpoint_enabled"] is False
    assert payload["vue_execution_controls_enabled"] is False
    assert payload["dry_run_required"] is True
    assert payload["explicit_approval_required"] is True
    assert payload["single_action_only_required"] is True
    assert payload["required_gates"]
    assert payload["blockers"]
