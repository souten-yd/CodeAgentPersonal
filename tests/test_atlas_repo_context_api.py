from fastapi.testclient import TestClient
from app.server import create_app
from agent.atlas_repo_index_storage import AtlasRepoIndexStorage


def test_repo_context_policies():
    c = TestClient(create_app())
    r = c.get('/api/atlas/repo-context/policies')
    assert r.status_code == 200


def test_repo_context_snapshot_api():
    c = TestClient(create_app())
    r = c.post('/api/atlas/repo-context/snapshot', json={})
    assert r.status_code == 200
    assert r.json()['status'] == 'missing'


def test_repo_context_scope_summary_uses_injected_data_root(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    project = tmp_path / "repo"
    project.mkdir()
    AtlasRepoIndexStorage(tmp_path).save_json(
        str(project.resolve()),
        "latest.json",
        {
            "workspace_id": "default",
            "project_path": str(project.resolve()),
            "index_run_id": "repoindex_api_root",
            "status": "indexed",
            "impacted_files": ["src/main.py"],
            "related_tests": ["tests/test_main.py"],
            "metadata": {"impacted_symbols": []},
        },
    )
    r = c.post('/api/atlas/repo-context/scope-summary', json={"project_path": str(project.resolve())})
    assert r.status_code == 200
    assert r.json().get("repo_index_snapshot", {}).get("index_run_id") == "repoindex_api_root"
