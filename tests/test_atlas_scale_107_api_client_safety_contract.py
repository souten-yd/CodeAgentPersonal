from pathlib import Path
TEXT=Path('web/atlas-next/src/api/atlasClient.ts').read_text()
def test_get_only_readiness_client_present():
    assert "'/api/atlas/level1/readiness'" in TEXT
    assert "method: 'GET'" in TEXT
    for t in ['/api/atlas/level1/execute','/dry-run','/approve','/apply','/rollback','/retry','/continue']:
        assert t not in TEXT
