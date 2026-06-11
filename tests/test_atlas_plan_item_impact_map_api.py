from fastapi.testclient import TestClient

from app.server import create_app


def test_endpoint_200(tmp_path):
    c = TestClient(create_app())
    r = c.post('/api/atlas/repo-context/plan-item-impact-map', json={"project_path": str(tmp_path), "plan_pool": {"items": [{"item_id": "1"}]}})
    assert r.status_code == 200
    body = r.json()
    assert "impacts" in body
    assert body.get("metadata", {}).get("advisory_only") is True
    assert body.get("metadata", {}).get("executed") is False
    assert body.get("metadata", {}).get("shell_executed") is False
    assert body.get("metadata", {}).get("remote_git_executed") is False
    assert body.get("metadata", {}).get("auto_verification_triggered") is False
    assert body.get("metadata", {}).get("auto_test_execution_triggered") is False


def test_file_path_400(tmp_path):
    c = TestClient(create_app())
    f = tmp_path / 'x.txt'; f.write_text('x')
    r = c.post('/api/atlas/repo-context/plan-item-impact-map', json={"project_path": str(f), "plan_pool": {"items": [{"item_id": "1"}]}})
    assert r.status_code == 400


def test_data_root_injected_and_missing_index_non_blocking(tmp_path, monkeypatch):
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path / 'atlas-root')
    captured = {}

    def fake_build_map(self, req):
        captured['data_root'] = str(self.data_root)
        from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMap
        return AtlasPlanItemImpactMap(status='missing')

    monkeypatch.setattr(
        'agent.project_intelligence.adapters.plan_item_impact_map.ProjectIntelligencePlanItemImpactMapAdapter.build_map',
        fake_build_map,
    )
    c = TestClient(app)
    r = c.post('/api/atlas/repo-context/plan-item-impact-map', json={"project_path": str(tmp_path), "plan_pool": {"items": [{"item_id": "1"}]}})
    assert r.status_code == 200
    assert 'atlas-root' in captured['data_root']
    assert r.json().get('status') in {'missing', 'empty_plan_pool', 'available'}
