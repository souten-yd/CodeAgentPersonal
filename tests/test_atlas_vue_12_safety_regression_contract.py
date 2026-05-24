from pathlib import Path


def _text(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def test_no_route_default_or_redirect_to_atlas_next() -> None:
    ui = _text('ui.html')
    server = _text('app/server.py').lower()

    assert 'atlas-next' not in ui.lower() or '/atlas-next' not in ui.lower()
    assert 'redirect("/atlas-next' not in server
    assert "redirect('/atlas-next" not in server


def test_vue_client_is_get_only_read_only_and_non_execution() -> None:
    client = _text('web/atlas-next/src/api/atlasClient.ts').lower()
    assert '/api/atlas/workflow-state/read-only' in client
    assert 'method: "post"' not in client
    assert 'method: "put"' not in client
    assert 'method: "patch"' not in client
    assert 'method: "delete"' not in client
    assert '/execute' not in client
    assert '/apply' not in client
    assert '/rollback' not in client


def test_preview_diagnostics_metadata_only_get() -> None:
    server = _text('app/server.py').lower()
    assert '@app.get("/api/atlas/vue-next-preview/diagnostics")' in server
    assert 'execution_enabled": false' in server
    assert 'mutation_endpoints_enabled": false' in server
    assert 'preview_health_state": "healthy" if valid else "fail_closed"' in server
