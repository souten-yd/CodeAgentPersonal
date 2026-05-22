from pathlib import Path


def test_vue_07_read_only_parity_contract() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    lower = client.lower()

    for required in [
        '/api/atlas/workflow-state/read-only',
        "method: 'GET'",
        'atlas.workflow_state.v1',
        'read_only_workflow_state',
        'fallbackWorkflowStateContract',
        'placeholder',
        'readOnly: true',
        'enabled: false',
        'autonomousExecutionEnabled: false',
        'vueExecutionEnabled: false',
        'backendWorkflowStateAuthoritative: true',
        'dryRunFirstPreserved: true',
        'executeOneActionPreserved: true',
        "source: accepted ? 'safe_get_adapter' : 'placeholder'",
        'staticMountDeferred: true',
        'routeMounted: false',
    ]:
        assert required in client

    for forbidden in [
        'method: "POST"', "method: 'POST'", 'method: "PUT"', "method: 'PUT'",
        'method: "PATCH"', "method: 'PATCH'", 'method: "DELETE"', "method: 'DELETE'",
        '/execute', '/apply', '/approve', '/safe_apply', '/rollback', '/restore', '/run', '/verify', '/retry', '/continue',
        'canExecute', 'executionEligible', 'isExecutionAllowed', 'eligibleForExecution',
    ]:
        assert forbidden.lower() not in lower
