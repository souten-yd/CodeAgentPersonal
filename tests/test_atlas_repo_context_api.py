from fastapi.testclient import TestClient
from app.server import create_app
from agent.atlas_repo_index_storage import AtlasRepoIndexStorage
from pathlib import Path


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


def test_impacted_tests_endpoint_uses_resolved_ca_data_root(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    project = tmp_path / "repo"
    project.mkdir()
    r = c.post('/api/atlas/repo-context/impacted-tests', json={"project_path": str(project.resolve())})
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "related_tests" in body
    assert "metadata" in body
    assert body["metadata"]["executed"] is False
    assert body["metadata"]["shell_executed"] is False
    assert body["metadata"]["remote_git_executed"] is False


def test_impacted_tests_endpoint_does_not_reference_resolve_data_root():
    source = Path("app/api/atlas_repo_context.py").read_text(encoding="utf-8")
    assert "resolve_data_root" not in source
    assert "resolve_atlas_ca_data_root(request)" in source


def test_impacted_tests_invalid_project_file_path(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    bad = tmp_path / "project.txt"
    bad.write_text("x", encoding="utf-8")
    r = c.post('/api/atlas/repo-context/impacted-tests', json={"project_path": str(bad.resolve())})
    assert r.status_code == 400


def test_impacted_tests_missing_index_non_blocking(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    project = tmp_path / "repo"
    project.mkdir()
    r = c.post('/api/atlas/repo-context/impacted-tests', json={"project_path": str(project.resolve())})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"missing", "partial"}
    assert body["metadata"]["executed"] is False
    assert body["metadata"]["shell_executed"] is False
    assert body["metadata"]["remote_git_executed"] is False
