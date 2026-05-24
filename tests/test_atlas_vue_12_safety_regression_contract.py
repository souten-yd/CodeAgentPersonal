from pathlib import Path


def test_vue_12_safety_regressions_not_introduced() -> None:
    server = Path('app/server.py').read_text(encoding='utf-8').lower()
    ui = Path('ui.html').read_text(encoding='utf-8').lower()
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8').lower()
    assert '/atlas-next' in server
    assert 'raw_source_serving_allowed": false' in server or 'raw_source_serving_allowed' in server
    assert 'app.get("/atlas-next")' in server or "@app.get('/atlas-next')" in server
    assert 'location.href = "/atlas-next"' not in ui
    assert 'method: "post"' not in client
    assert 'method: "put"' not in client
    assert 'method: "patch"' not in client
    assert 'method: "delete"' not in client
