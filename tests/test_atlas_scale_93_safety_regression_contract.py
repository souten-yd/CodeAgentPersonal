from pathlib import Path


def test_vue_client_has_no_execution_or_mutation_endpoints() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert '/api/atlas/workflow-state/read-only' in text
    assert '/api/atlas/plan-pools' in text
    forbidden = [
        '/dry-run', '/execute', '/apply', '/approve', '/rollback', '/restore', '/verify', '/retry', '/continue',
        '/safe-apply/execute', '/auto-safe-apply', '/auto-safe-apply-and-verify', '/approvals/decide', '/automation/',
    ]
    for fragment in forbidden:
        assert fragment not in text


def test_runtime_and_autonomous_flags_stay_disabled() -> None:
    contract_text = Path('app/atlas/workflow_state_contract.py').read_text(encoding='utf-8')
    assert '"runtime_level": "level_0_manual_only"' in contract_text
    assert '"autonomous_execution_enabled": False' in contract_text
    assert '"level1_execution_enabled": False' in contract_text
