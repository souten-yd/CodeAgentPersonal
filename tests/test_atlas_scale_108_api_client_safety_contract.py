from pathlib import Path

def test_api_client_readiness_get_only():
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert '/api/atlas/level1/readiness' in text
    assert 'method: \"POST\"' not in text
    assert 'method: \"PUT\"' not in text
    assert 'method: \"PATCH\"' not in text
    assert 'method: \"DELETE\"' not in text
