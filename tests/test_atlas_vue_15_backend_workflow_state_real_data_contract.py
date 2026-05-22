from app.atlas.workflow_state_contract import build_read_only_workflow_state


def test_vue_15_backend_workflow_state_real_data_contract() -> None:
    payload = build_read_only_workflow_state(goal='g', project_path='p', phase='read_only_preview', status='ok', primary_cta_label='Read-only')
    assert payload['contract'] == 'read_only_workflow_state'
    meta = payload['workflow_state_metadata']
    for key in ['latest_pool_id', 'latest_run_id', 'continuation_state', 'recovery_state', 'data_freshness', 'source_detail']:
        assert key in meta
    assert meta['data_freshness'] == 'unknown'
    assert payload['vue_execution_enabled'] is False
    assert payload['safety']['mutation_endpoints_enabled'] is False
