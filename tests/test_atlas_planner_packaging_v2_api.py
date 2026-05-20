from fastapi.testclient import TestClient
from app.server import create_app
import app.api.atlas_repo_context as api_mod


def test_endpoint_200_shape_and_metadata_flags(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    c = TestClient(app)
    r = c.post('/api/atlas/repo-context/planner-packaging-v2', json={'project_path': str(tmp_path)})
    assert r.status_code == 200
    b = r.json()
    for k in ['status', 'planner_context_text', 'context_sections', 'metadata', 'impacted_files', 'related_tests']:
        assert k in b
    m = b['metadata']
    assert m['advisory_only'] is True and m['executed'] is False and m['shell_executed'] is False
    assert m['remote_git_executed'] is False and m['auto_verification_triggered'] is False and m['auto_test_execution_triggered'] is False


def test_endpoint_injects_request_data_root(tmp_path, monkeypatch):
    captured = {}
    original = api_mod.AtlasPlannerPackagingV2Service.build_package

    def wrapped(self, req):
        captured['data_root'] = str(self.data_root)
        return original(self, req)

    monkeypatch.setattr(api_mod.AtlasPlannerPackagingV2Service, 'build_package', wrapped)
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path / 'custom_root')
    c = TestClient(app)
    r = c.post('/api/atlas/repo-context/planner-packaging-v2', json={'project_path': str(tmp_path)})
    assert r.status_code == 200
    assert captured['data_root'].endswith('custom_root')
