from pathlib import Path


def test_vue_15_client_real_data_normalization_contract() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    for needle in [
        'workflow_state_metadata',
        'normalizeWorkflowMetadata',
        'planPoolAvailable',
        'fetch(\'/api/atlas/workflow-state/read-only\', { method: \'GET\' })',
        'backendAuthorityNote',
    ]:
        assert needle in text
    low = text.lower()
    for m in ["method: 'post'", "method: 'put'", "method: 'patch'", "method: 'delete'"]:
        assert m not in low
