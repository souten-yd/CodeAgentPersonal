from pathlib import Path


def test_vue_13_safety_regressions() -> None:
    ui = Path('ui.html').read_text(encoding='utf-8').lower()
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8').lower()
    server = Path('app/server.py').read_text(encoding='utf-8').lower()

    assert 'location.href = "/atlas-next"' not in ui
    assert 'method: "post"' not in client
    assert 'method: "put"' not in client
    assert 'method: "patch"' not in client
    assert 'method: "delete"' not in client

    assert '@app.get("/atlas-next")' in server
    assert 'execution_enabled": false' in server or "'execution_enabled': false" in server
    assert 'mutation_endpoints_enabled": false' in server or "'mutation_endpoints_enabled': false" in server
