from pathlib import Path
TEXT=Path('web/atlas-next/src/api/atlasClient.ts').read_text()

def test_api_client_readiness_endpoint_get_only():
    assert "/api/atlas/level1/readiness" in TEXT
    assert "method: 'GET'" in TEXT

def test_no_history_or_diff_mutation_endpoints():
    forbidden=['/level1/readiness/history','/level1/readiness/diff','/level1/readiness/import','/level1/readiness/export']
    for token in forbidden:
        assert token not in TEXT
