from pathlib import Path

from fastapi.testclient import TestClient

from app.server import create_app


def test_context_refresh_v2_api_ok_and_data_root_injected(tmp_path: Path, monkeypatch):
    app = create_app()
    custom_root = tmp_path / 'custom-root'
    app.state.atlas_ca_data_root = custom_root
    captured = {}

    from agent.project_intelligence.adapters import context_refresh_v2 as svc_mod

    orig_refresh = svc_mod.ProjectIntelligenceContextRefreshV2Adapter.refresh

    def wrapped(self, req):
        captured['data_root'] = str(self.data_root)
        return orig_refresh(self, req)

    monkeypatch.setattr(svc_mod.ProjectIntelligenceContextRefreshV2Adapter, 'refresh', wrapped)
    c = TestClient(app)
    res = c.post('/api/atlas/context-refresh/v2', json={'project_path': str(tmp_path), 'plan_pool': {'items': []}})
    assert res.status_code == 200
    assert 'custom-root' in captured['data_root']
    d = res.json()
    assert all(k in d for k in ['status', 'plan_item_impact', 'impacted_files', 'related_tests', 'metadata'])
    assert d['metadata']['executed'] is False and d['metadata']['advisory_only'] is True


def test_context_refresh_v2_api_rejects_file(tmp_path: Path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    f = tmp_path / 'x.txt'; f.write_text('x')
    c = TestClient(app)
    res = c.post('/api/atlas/context-refresh/v2', json={'project_path': str(f)})
    assert res.status_code == 400


def test_context_refresh_v2_missing_plan_pool_non_blocking(tmp_path: Path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    res = c.post('/api/atlas/context-refresh/v2', json={'project_path': str(tmp_path)})
    assert res.status_code == 200
    assert res.json()['status'] in {'missing', 'empty_plan_pool'}
