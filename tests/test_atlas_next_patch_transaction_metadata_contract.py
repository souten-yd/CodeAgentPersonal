from pathlib import Path


def test_atlas_next_patch_review_panel_uses_backend_transaction_metadata() -> None:
    panel = Path('web/atlas-next/src/components/PatchReviewPanel.vue').read_text(encoding='utf-8')
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')

    for needle in [
        'snapshot.patchTransaction.source',
        'transaction.available',
        'transaction.transactionId',
        'transaction.candidateCount',
        'snapshot.patchTransaction.previewStatus',
        'snapshot.patchTransaction.riskClass',
        'snapshot.patchTransaction.rollbackReady',
        'snapshot.patchTransaction.warnings',
        'display-only',
    ]:
        assert needle in panel

    assert 'AtlasPatchTransactionMetadata' in client
    assert 'patch_transaction_metadata?: Record<string, unknown>' in client
    assert 'DEFAULT_PATCH_TRANSACTION_METADATA' in client


def test_atlas_next_patch_transaction_metadata_does_not_enable_actions() -> None:
    panel = Path('web/atlas-next/src/components/PatchReviewPanel.vue').read_text(encoding='utf-8').lower()
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')

    for forbidden in ['generatepatch', 'applypatch', 'verifypatch', 'rollbackpatch']:
        assert forbidden.lower() not in panel
        assert forbidden not in client

    for needle in [
        'generationEnabled: false',
        'applyEnabled: false',
        'safeApplyEnabled: false',
        'verificationEnabled: false',
        'rollbackEnabled: false',
        'advisoryOnly: true',
    ]:
        assert needle in client


def test_backend_workflow_state_contract_exposes_patch_preview_detail_fields() -> None:
    text = Path('app/atlas/workflow_state_contract.py').read_text(encoding='utf-8')
    for needle in [
        '"preview_status": metadata_payload.get("patch_transaction_preview_status", "missing")',
        '"risk_class": metadata_payload.get("patch_transaction_risk_class", "unknown")',
        '"rollback_ready": bool(metadata_payload.get("patch_transaction_rollback_ready", False))',
        '"warnings": _coerce_string_list(metadata_payload.get("patch_transaction_warnings"))',
    ]:
        assert needle in text
