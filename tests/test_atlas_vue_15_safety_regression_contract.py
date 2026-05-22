from pathlib import Path


def test_vue_15_safety_regression_contract() -> None:
    ui = Path('ui.html').read_text(encoding='utf-8').lower()
    server = Path('app/server.py').read_text(encoding='utf-8').lower()
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8').lower()
    assert 'location.href = "/atlas-next"' not in ui
    assert '@app.get("/atlas-next")' in server or "@app.get('/atlas-next')" in server
    assert '/api/atlas/workflow-state/read-only' in client
    assert 'execution eligibility' in client
    for method in ["method: 'post'", "method: 'put'", "method: 'patch'", "method: 'delete'"]:
        assert method not in client
