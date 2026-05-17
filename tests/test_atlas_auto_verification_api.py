from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def test_allowlist_and_new_routes_exist(tmp_path):
    c = _client(tmp_path)
    r = c.get('/api/atlas/verification/allowlist')
    assert r.status_code == 200
    body = r.json()
    ids = {x['command_id'] for x in body['commands']}
    assert {'pytest_selected','pytest_file','node_check_dashboard','node_check_pipeline_api'} <= ids
