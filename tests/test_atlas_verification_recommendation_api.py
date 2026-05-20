from pathlib import Path
from fastapi.testclient import TestClient
from app.server import create_app

def test_endpoint_200_and_shape(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    c=TestClient(app)
    r=c.post('/api/atlas/repo-context/verification-recommendation', json={'project_path': str(tmp_path)})
    assert r.status_code==200
    d=r.json()
    for k in ['status','summary','impacted_files','related_tests','recommended_commands','manual_verification_steps','metadata']:
        assert k in d
    m=d['metadata']
    assert m['advisory_only'] is True and m['executed'] is False and m['shell_executed'] is False and m['remote_git_executed'] is False and m['auto_verification_triggered'] is False and m['auto_test_execution_triggered'] is False

def test_invalid_project_path_file_returns_400(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    c=TestClient(app)
    f=tmp_path/'x.txt'; f.write_text('x')
    r=c.post('/api/atlas/repo-context/verification-recommendation', json={'project_path': str(f)})
    assert r.status_code==400

def test_data_root_injected(tmp_path):
    app = create_app()
    root=tmp_path/'ca'; root.mkdir()
    app.state.atlas_ca_data_root=str(root)
    c=TestClient(app)
    r=c.post('/api/atlas/repo-context/verification-recommendation', json={'project_path': str(tmp_path)})
    assert r.status_code==200
