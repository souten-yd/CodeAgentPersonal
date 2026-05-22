from pathlib import Path


def test_vue_next_adapter_exports_and_read_only_normalization() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    for exported in [
        'export type AtlasReadOnlyAvailableAction =',
        'export type AtlasReadOnlySafetyState =',
        'export type AtlasWorkflowSnapshot =',
        'export type AtlasWorkflowArtifactState =',
        'export type AtlasWorkflowDiagnosticsState =',
    ]:
        assert exported in client

    assert 'readOnly: true' in client
    assert 'enabled: false' in client
    assert 'return { id, label, kind, readOnly: true, enabled: false' in client


def test_vue_next_adapter_has_no_mutation_or_execution_calls() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8').lower()
    for forbidden in [
        'method: "post"',
        "method: 'post'",
        'method: "put"',
        "method: 'put'",
        'method: "patch"',
        "method: 'patch'",
        'method: "delete"',
        "method: 'delete'",
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


def test_vue_next_adapter_v04_decision_fields() -> None:
    manifest = __import__('json').loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['vue_next_get_adapter_decision'] in {'deferred_no_stable_get_contract', 'connected_safe_get', 'contract_defined_binding_deferred'}
    assert manifest['vue_next_backend_get_adapter_connected'] in {True, False}
    assert manifest['vue_next_backend_contract_ready'] in {True, False}
