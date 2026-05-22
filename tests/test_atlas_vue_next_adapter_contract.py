from pathlib import Path


def test_vue_next_adapter_exports_and_read_only_normalization() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    for exported in [
        'export type AtlasReadOnlyAvailableAction =',
        'export type AtlasReadOnlySafetyState =',
        'export type AtlasWorkflowSnapshot =',
    ]:
        assert exported in client

    assert 'readOnly: true' in client
    assert 'enabled: false' in client
    assert 'return { id, label, kind, readOnly: true, enabled: false' in client


def test_vue_next_adapter_has_no_mutation_or_execution_calls() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8').lower()
    for forbidden in [
        'fetch(',
        'method: "post"',
        "method: 'post'",
        '/execute',
        '/apply',
        '/approve',
        '/safe_apply',
        '/rollback',
        '/restore',
        '/run',
        '/verify',
        '/retry',
        '/continue',
    ]:
        assert forbidden not in client


def test_vue_next_adapter_backend_authoritative_and_no_execution_eligibility_logic() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert 'backendWorkflowStateAuthoritative: true' in client
    assert 'backend workflow_state contract endpoint' in client
    for forbidden_logic in [
        'executionEligible',
        'canExecute',
        'eligibleForExecution',
        'isExecutionAllowed',
    ]:
        assert forbidden_logic not in client
