from pathlib import Path


def test_api_client_readiness_get_only_and_no_mutation_verbs():
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "fetch('/api/atlas/level1/readiness', { method: 'GET' })" in text
    for bad in ['POST', 'PUT', 'PATCH', 'DELETE']:
        assert f"/api/atlas/level1/readiness', {{ method: '{bad}'" not in text
