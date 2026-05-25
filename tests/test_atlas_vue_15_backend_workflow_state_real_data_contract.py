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

    patch = payload['patch_transaction_metadata']
    assert patch['available'] is False
    assert patch['candidate_count'] == 0
    assert patch['source'] == 'backend_contract_metadata_only'
    assert patch['generation_enabled'] is False
    assert patch['apply_enabled'] is False
    assert patch['safe_apply_enabled'] is False
    assert patch['verification_enabled'] is False
    assert patch['rollback_enabled'] is False
    assert patch['advisory_only'] is True


def test_vue_15_backend_patch_transaction_metadata_is_display_only() -> None:
    payload = build_read_only_workflow_state(
        goal='g',
        project_path='p',
        phase='read_only_preview',
        status='ok',
        primary_cta_label='Read-only',
        artifacts={'transaction': True},
        workflow_metadata={
            'latest_patch_transaction_id': 'txn-123',
            'patch_candidate_count': 2,
            'patch_transaction_source': 'backend_patch_preview',
        },
    )

    patch = payload['patch_transaction_metadata']
    assert patch['available'] is True
    assert patch['transaction_id'] == 'txn-123'
    assert patch['candidate_count'] == 2
    assert patch['source'] == 'backend_patch_preview'
    assert patch['generation_enabled'] is False
    assert patch['apply_enabled'] is False
    assert patch['safe_apply_enabled'] is False
    assert patch['verification_enabled'] is False
    assert patch['rollback_enabled'] is False
    assert patch['advisory_only'] is True
    assert payload['safety']['automatic_patch_generation_enabled'] is False
    assert payload['safety']['automatic_patch_apply_enabled'] is False
