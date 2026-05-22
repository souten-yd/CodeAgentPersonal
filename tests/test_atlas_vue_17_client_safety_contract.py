from pathlib import Path

def test_vue_client_only_expected_endpoints_and_safe_payload_defaults() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "fetch('/api/atlas/workflow-state/read-only'" in text
    assert "fetch('/api/atlas/plan-pools'" in text
    assert "automation_level: 'plan_then_ask'" in text
    assert "execution_strategy: 'sequential'" in text
    assert "automation_level: request.automation_level ?? 'plan_then_ask'" in text
    assert "execution_strategy: request.execution_strategy ?? 'sequential'" in text
