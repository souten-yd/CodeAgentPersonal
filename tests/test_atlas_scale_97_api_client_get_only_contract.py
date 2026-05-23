from pathlib import Path


def test_scale_97_api_client_get_only_helper() -> None:
    t = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert 'fetchLevel1ReadinessDiagnostics' in t
    assert "'/api/atlas/level1/readiness'" in t
    assert "method: 'GET'" in t
