from fastapi.testclient import TestClient
from app.server import create_app
import app.api.atlas_pipeline as pipeline_mod


def test_planpool_repo_context_enables_packaging(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    c = TestClient(app)
    r = c.post('/api/atlas/plan-pools?sync=1', json={'input': 'g', 'project_path': str(tmp_path), 'enable_repo_context': True})
    assert r.status_code == 200
    md = r.json()['plan_pool']['metadata']
    assert 'planner_packaging_v2' in md and 'planner_context_text_v2' in md
    p = md['planner_packaging_v2']
    assert p['advisory_only'] is True and p['executed'] is False
    assert len(p.get('impacted_files', [])) <= 30 and len(p.get('related_tests', [])) <= 20 and len(p.get('recommended_commands', [])) <= 5


def test_planpool_repo_context_disabled_no_active_packaging(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    c = TestClient(app)
    r = c.post('/api/atlas/plan-pools?sync=1', json={'input': 'g', 'project_path': str(tmp_path), 'enable_repo_context': False})
    assert r.status_code == 200
    md = r.json()['plan_pool']['metadata']
    assert ('planner_packaging_v2' not in md) or (md.get('planner_packaging_v2', {}).get('status') in {'missing', 'inactive', None})


def test_planpool_packaging_failure_non_blocking(tmp_path, monkeypatch):
    def boom(self, req):
        raise RuntimeError('fail')
    monkeypatch.setattr(pipeline_mod.AtlasRepoContextAdapter, 'build_planner_packaging_v2', boom)
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    c = TestClient(app)
    r = c.post('/api/atlas/plan-pools?sync=1', json={'input': 'g', 'project_path': str(tmp_path), 'enable_repo_context': True})
    assert r.status_code == 200
    md = r.json()['plan_pool']['metadata']
    assert 'planner_packaging_v2' not in md or md.get('planner_packaging_v2', {}).get('status') in {'missing', 'failed', 'partial'}
