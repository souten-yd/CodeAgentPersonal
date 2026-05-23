from pathlib import Path

def test_api_client_readiness_get_only_no_execution_endpoint_call():
    t = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "fetch('/api/atlas/level1/readiness', { method: 'GET' })" in t
    assert '/api/atlas/level1/execute' not in t
