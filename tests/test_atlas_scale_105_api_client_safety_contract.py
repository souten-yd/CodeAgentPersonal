from pathlib import Path
TEXT=Path('web/atlas-next/src/api/atlasClient.ts').read_text()

def test_readiness_endpoint_remains_get_only():
    assert "'/api/atlas/level1/readiness'" in TEXT
    assert "method: 'GET'" in TEXT

def test_no_diff_filtering_or_execution_endpoints_in_api_client():
    for token in ['/api/atlas/level1/execute','/dry-run','/approve','/apply','/rollback','/retry','/continue','history/diff/filter']:
        assert token not in TEXT
