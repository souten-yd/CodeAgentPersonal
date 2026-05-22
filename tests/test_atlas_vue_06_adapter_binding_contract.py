from pathlib import Path


def test_vue_06_adapter_binding_contract() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    lower = client.lower()

    for required in [
        '/api/atlas/workflow-state/read-only',
        'fetch(',
        'atlas.workflow_state.v1',
        'read_only_workflow_state',
        'safe_get_adapter',
        'placeholder',
        'backendWorkflowStateAuthoritative: true',
        'readOnly: true',
        'enabled: false',
    ]:
        assert required in client

    for forbidden in [
        'method: "POST"', "method: 'POST'", 'method: "PUT"', "method: 'PUT'",
        'method: "PATCH"', "method: 'PATCH'", 'method: "DELETE"', "method: 'DELETE'",
        '/execute', '/apply', '/approve', '/safe_apply', '/rollback', '/restore', '/run', '/verify', '/retry', '/continue',
        'canExecute', 'executionEligible', 'isExecutionAllowed', 'eligibleForExecution',
    ]:
        assert forbidden.lower() not in lower
