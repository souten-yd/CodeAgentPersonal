from pathlib import Path

def test_api_client_get_only_for_readiness():
    t = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "fetch('/api/atlas/level1/readiness', { method: 'GET' })" in t
    assert '/api/atlas/level1/execute' not in t
