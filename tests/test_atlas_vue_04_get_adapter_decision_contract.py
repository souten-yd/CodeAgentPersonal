from pathlib import Path
import json


def test_vue_04_get_adapter_decision_contract() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    decision = manifest['vue_next_get_adapter_decision']
    assert decision in {'deferred_no_stable_get_contract', 'connected_safe_get', 'contract_defined_binding_deferred'}

    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    lower = client.lower()

    assert 'readOnly: true' in client
    assert 'enabled: false' in client
    assert 'backendWorkflowStateAuthoritative: true' in client
    for forbidden_logic in ['executionEligible', 'canExecute', 'eligibleForExecution', 'isExecutionAllowed']:
        assert forbidden_logic not in client

    if decision == 'deferred_no_stable_get_contract':
        assert manifest['vue_next_backend_get_adapter_connected'] is False
        assert manifest['vue_next_backend_contract_ready'] is False
        assert "source: 'placeholder'" in client or 'source: "placeholder"' in client
        assert 'backendContractReady: false' in client
    elif decision == 'connected_safe_get':
        assert 'fetch(' in lower
        for forbidden in ['method: "post"', "method: 'post'", 'method: "put"', 'method: "patch"', 'method: "delete"']:
            assert forbidden not in lower
        for forbidden_path in ['/execute','/apply','/approve','/safe_apply','/rollback','/restore','/run','/verify','/retry','/continue']:
            assert forbidden_path not in lower
        assert 'safe_get_adapter' in client


def test_vue_05_contract_defined_binding_deferred_manifest_state() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    if manifest['vue_next_get_adapter_decision'] == 'contract_defined_binding_deferred':
        assert manifest['vue_next_backend_contract_ready'] is True
        assert manifest['vue_next_backend_get_adapter_connected'] is False
