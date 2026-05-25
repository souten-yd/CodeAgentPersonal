from pathlib import Path


def test_atlas_next_patch_review_panel_uses_backend_transaction_metadata() -> None:
    panel = Path('web/atlas-next/src/components/PatchReviewPanel.vue').read_text(encoding='utf-8')
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')

    for needle in [
        'snapshot.patchTransaction.source',
        'transaction.available',
        'transaction.transactionId',
        'transaction.candidateCount',
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
