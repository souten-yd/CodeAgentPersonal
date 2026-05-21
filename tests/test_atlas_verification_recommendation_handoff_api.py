from fastapi.testclient import TestClient
from app.server import create_app


def test_handoff_endpoint_200_and_shape(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root = str(tmp_path); c = TestClient(app)
    r = c.post('/api/atlas/repo-context/verification-recommendation-handoff', json={"project_path":".","verification_recommendation":{"status":"ok"}})
    assert r.status_code == 200
    d = r.json()
    for k in ["status","approval_summary","impacted_files","related_tests","recommended_commands","manual_verification_steps","handoff_metadata","metadata"]:
      assert k in d


def test_handoff_endpoint_invalid_file_path_400(tmp_path):
    f = tmp_path / 'a.txt'; f.write_text('x')
    app=create_app(); c = TestClient(app)
    r = c.post('/api/atlas/repo-context/verification-recommendation-handoff', json={"project_path":str(f)})
    assert r.status_code == 400
