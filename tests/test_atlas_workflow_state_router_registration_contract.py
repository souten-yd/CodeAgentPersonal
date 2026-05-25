from pathlib import Path


def test_workflow_state_router_registered_before_legacy_pipeline_router() -> None:
    text = Path('app/server.py').read_text(encoding='utf-8')
    assert 'from app.api.atlas_workflow_state import router as atlas_workflow_state_router' in text
    assert 'app.include_router(atlas_workflow_state_router)' in text
    assert text.index('app.include_router(atlas_workflow_state_router)') < text.index('app.include_router(atlas_pipeline_router)')


def test_workflow_state_router_uses_patch_transaction_preview_metadata() -> None:
    text = Path('app/api/atlas_workflow_state.py').read_text(encoding='utf-8')
    assert 'build_latest_patch_transaction_workflow_metadata' in text
    assert 'patch_transaction_metadata = build_latest_patch_transaction_workflow_metadata(data_root=ca_data_root)' in text
    assert '**patch_transaction_metadata' in text
    assert 'patch_transaction_metadata["patch_transaction_available"]' in text
    for forbidden in ['safe_apply', 'execute_one', 'verify_one', 'rollback']:
        assert forbidden not in text
