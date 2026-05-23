from pathlib import Path


def test_scale_98_api_client_readiness_is_get_only() -> None:
    t = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "'/api/atlas/level1/readiness'" in t
    assert "method: 'GET'" in t
    readiness_slice = t.split("'/api/atlas/level1/readiness'", 1)[1][:220]
    for verb in ['POST', 'PUT', 'PATCH', 'DELETE']:
        assert f"method: '{verb}'" not in readiness_slice
