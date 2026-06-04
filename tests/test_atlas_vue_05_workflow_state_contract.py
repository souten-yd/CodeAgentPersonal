from fastapi.testclient import TestClient

import main
from app.atlas.workflow_state_contract import (
    build_read_only_workflow_state,
    normalize_read_only_available_actions,
    summarize_workflow_state_contract,
)


def test_workflow_state_contract_helpers_emit_read_only_metadata_only() -> None:
    actions = normalize_read_only_available_actions([{"id": "execute", "label": "Execute", "kind": "mutation"}])
    assert actions[0]["read_only"] is True
    assert actions[0]["enabled"] is False
    assert actions[0]["requires_confirmation"] is True
    assert actions[0]["requires_dry_run"] is True

    payload = build_read_only_workflow_state(
        goal="g",
        project_path="p",
        phase="ph",
        status="st",
        primary_cta_label="label",
        available_actions=actions,
    )
    assert payload["schema_version"] == "atlas.workflow_state.v1"
    assert payload["contract"] == "read_only_workflow_state"
    assert payload["backend_workflow_state_authoritative"] is True
    assert payload["vue_source_of_truth"] is False
    assert payload["autonomous_execution_enabled"] is False
    assert payload["preview_runtime_level"] == "level_4_self_improvement_platform"
    assert payload["level1_execution_enabled"] is True
    assert payload["diagnostics"]["backend_contract_ready"] is True
    summary = summarize_workflow_state_contract(payload)
    assert summary["manual_only"] is True
    assert summary["available_action_count"] == 1


def test_workflow_state_read_only_route_contract() -> None:
    response = TestClient(main.app).get('/api/atlas/workflow-state/read-only')
    assert response.status_code == 200
    payload = response.json()
    assert payload['schema_version'] == 'atlas.workflow_state.v1'
    assert payload['contract'] == 'read_only_workflow_state'
    assert payload['source'] == 'backend_contract'
    assert payload['runtime_level'] == 'level_0_review_only'
    assert payload['backend_workflow_state_authoritative'] is True
    assert payload['vue_source_of_truth'] is False
    assert payload['vue_execution_enabled'] is False
    assert payload['autonomous_execution_enabled'] is False
    assert payload['level1_execution_enabled'] is False
    assert payload['primary_cta']['state'] == 'read_only'
    assert payload['primary_cta']['enabled'] is False
    assert payload['diagnostics']['backend_contract_ready'] is True
    assert all(a['enabled'] is False and a['read_only'] is True for a in payload['available_actions'])
    patch = payload['patch_transaction_metadata']
    assert patch['available'] is False
    assert patch['generation_enabled'] is False
    assert patch['apply_enabled'] is False
    assert patch['safe_apply_enabled'] is False
    assert patch['verification_enabled'] is False
    assert patch['rollback_enabled'] is False
    assert patch['advisory_only'] is True
