from app.atlas.level1_guarded_execution import (
    build_level1_disabled_readiness_result,
    build_level1_gate_source_map,
)


CANONICAL_GATES = {
    'snapshot_restore',
    'patch_transaction',
    'risk_classification',
    'dry_run_proof',
    'explicit_approval_token',
    'allowlisted_verification',
    'rollback_readiness',
    'artifact_capture',
    'stop_kill_switch',
    'loop_bounds',
    'remote_git_restriction',
    'self_improvement_gate',
    'audit_log',
    'data_root_path_safety',
    'forbidden_command_execution_policy',
    'backend_authority_enforcement',
    'ui_non_authority_enforcement',
}


def test_scale_96_gate_source_mapping_contract() -> None:
    gate_map = build_level1_gate_source_map()
    ids = {item['gate_id'] for item in gate_map}
    assert ids == CANONICAL_GATES

    disabled = build_level1_disabled_readiness_result()
    assert set(disabled.required_gates) == CANONICAL_GATES
    assert {item.gate for item in disabled.blockers} == CANONICAL_GATES

    for item in gate_map:
        for key in ('owner', 'source', 'evidence_required', 'blocker_reason', 'test_requirement'):
            assert item.get(key)
        assert item['mutable'] is False
        assert item['advisory_only'] is True
