from pathlib import Path
API=Path('web/atlas-next/src/api/atlasClient.ts').read_text()

def test_readiness_get_only_client():
    assert '/api/atlas/level1/readiness' in API
    assert 'method: \'GET\'' in API
