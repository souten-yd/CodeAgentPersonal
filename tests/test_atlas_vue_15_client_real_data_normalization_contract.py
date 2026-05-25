from pathlib import Path


def test_vue_15_client_real_data_normalization_contract() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    for needle in [
        'workflow_state_metadata',
        'normalizeWorkflowMetadata',
        'patch_transaction_metadata',
        'normalizePatchTransactionMetadata',
        'patchTransaction: normalizePatchTransactionMetadata(payload.patch_transaction_metadata)',
        'planPoolAvailable',
        'fetch(\'/api/atlas/workflow-state/read-only\', { method: \'GET\' })',
        'backendAuthorityNote',
    ]:
        assert needle in text
    low = text.lower()
    assert "fetch('/api/atlas/plan-pools'" in text
    for m in ["method: 'put'", "method: 'patch'", "method: 'delete'"]:
        assert m not in low


def test_vue_15_client_patch_transaction_normalization_stays_display_only() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    for needle in [
        'generationEnabled: false',
        'applyEnabled: false',
        'safeApplyEnabled: false',
        'verificationEnabled: false',
        'rollbackEnabled: false',
        'advisoryOnly: true',
        'available: item.available === true',
        'candidateCount',
        'transactionId',
        'previewStatus',
        'riskClass',
        'rollbackReady: item.rollback_ready === true',
        'warnings.filter',
    ]:
        assert needle in text
