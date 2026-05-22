from pathlib import Path


def test_vue_14_client_diagnostics_alignment_contract() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert 'routeMounted: false' not in text
    assert 'staticMountDeferred: true' not in text
    for required in [
        "routeMounted: true",
        "routePath: '/atlas-next'",
        "routeDefault: false",
        "routeGuarded: true",
        "distBacked: true",
        "failClosed: true",
        "staticMountDeferred: false",
        "diagnosticsEndpoint: '/api/atlas/vue-next-preview/diagnostics'",
    ]:
        assert required in text
    assert "fetch('/api/atlas/workflow-state/read-only', { method: 'GET' })" in text
    lowered = text.lower()
    assert "fetch('/api/atlas/plan-pools'" in text
    assert "method: 'put'" not in lowered
    assert "method: 'patch'" not in lowered
    assert "method: 'delete'" not in lowered
