from fastapi.testclient import TestClient
from app.server import create_app
from agent.atlas_repo_context_planner_packager import AtlasRepoContextPlannerPackager


def test_create_plan_pool_succeeds_when_repo_index_missing():
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': '/tmp/not-found-repo'})
    assert r.status_code == 200
    assert r.json()['status'] == 'ready'


def test_create_plan_pool_repo_context_disabled(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    project = tmp_path / "repo"
    project.mkdir()
    r = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': str(project), 'enable_repo_context': False})
    assert r.status_code == 200
    repo_context = r.json().get('metadata', {}).get('repo_context')
    assert repo_context is None or repo_context.get('status') == 'disabled'


def test_create_plan_pool_preflight_uses_top_level_changed_files(monkeypatch):
    captured = {}
    original = AtlasRepoContextPlannerPackager.build_package

    def _capture(self, request):
        captured["changed_files"] = list(request.changed_files)
        captured["target_files"] = list(request.target_files)
        return original(self, request)

    monkeypatch.setattr(AtlasRepoContextPlannerPackager, "build_package", _capture)
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={
        'input': 'x',
        'project_path': '/tmp/not-found-repo',
        'changed_files': ['app/foo.py'],
        'target_files': ['app/bar.py'],
        'metadata': {'changed_files': ['wrong/a.py'], 'target_files': ['wrong/b.py']},
    })
    assert r.status_code == 200
    assert captured["changed_files"] == ['app/foo.py']
    assert captured["target_files"] == ['app/bar.py']


def test_create_plan_pool_metadata_changed_files_fallback_only_when_top_level_empty(monkeypatch):
    captured = {}
    original = AtlasRepoContextPlannerPackager.build_package

    def _capture(self, request):
        captured["changed_files"] = list(request.changed_files)
        captured["target_files"] = list(request.target_files)
        return original(self, request)

    monkeypatch.setattr(AtlasRepoContextPlannerPackager, "build_package", _capture)
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={
        'input': 'x',
        'project_path': '/tmp/not-found-repo',
        'changed_files': [],
        'target_files': [],
        'metadata': {'changed_files': ['legacy/a.py'], 'target_files': ['legacy/b.py']},
    })
    assert r.status_code == 200
    assert captured["changed_files"] == ['legacy/a.py']
    assert captured["target_files"] == ['legacy/b.py']


def test_create_plan_pool_impacted_test_recommendation_executed_false():
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': '/tmp/not-found-repo'})
    assert r.status_code == 200
    rec = r.json().get("plan_pool", {}).get("metadata", {}).get("repo_context", {}).get("impacted_test_recommendation", {})
    rec_meta = rec.get("metadata", {})
    assert rec_meta.get("executed", False) is False
    assert rec_meta.get("shell_executed", False) is False
    assert rec_meta.get("remote_git_executed", False) is False
