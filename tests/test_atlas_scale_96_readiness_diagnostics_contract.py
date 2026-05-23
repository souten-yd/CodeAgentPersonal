from fastapi.testclient import TestClient

from main import app


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


def test_scale_96_readiness_diagnostics_contract() -> None:
    payload = TestClient(app).get('/api/atlas/level1/readiness').json()
    assert isinstance(payload.get('gate_source_map'), list)
    assert isinstance(payload.get('evidence_summary'), dict)
    assert payload['mutation_performed'] is False
    assert payload['execution_performed'] is False
    assert payload['advisory_only'] is True
    assert payload['missing_evidence_count'] >= 0
    assert payload['runtime_level'] == 'level_0_manual_only'
    assert payload['level1_execution_enabled'] is False
    assert payload['enabled'] is False

    required = set(payload.get('required_gates', []))
    mapped = {item['gate_id'] for item in payload.get('gate_source_map', [])}
    blockers = {item['gate'] for item in payload.get('blockers', [])}
    assert required == CANONICAL_GATES
    assert mapped == CANONICAL_GATES
    assert blockers == CANONICAL_GATES
