from fastapi.testclient import TestClient

import main


def test_code_intel_endpoints_read_only_and_project_path_required(tmp_path):
    client = TestClient(main.app)
    r = client.post('/api/atlas/code-intel/symbol-index', json={})
    assert r.status_code == 422

    repo = tmp_path / 'repo'; repo.mkdir()
    (repo / 'a.py').write_text('import os\n', encoding='utf-8')
    ok1 = client.post('/api/atlas/code-intel/symbol-index', json={'project_path': str(repo)})
    ok2 = client.post('/api/atlas/code-intel/dependency-graph', json={'project_path': str(repo)})
    ok3 = client.post('/api/atlas/code-intel/related-tests', json={'project_path': str(repo), 'changed_files': ['a.py']})
    assert ok1.status_code == 200 and ok2.status_code == 200 and ok3.status_code == 200

    bad = client.post('/api/atlas/code-intel/symbol-index', json={'project_path': str(repo), 'relative_path': '../x'})
    assert bad.status_code == 400
    assert bad.json()['detail']['error'] == 'invalid_request'
    assert bad.json()['detail']['reason']

    for method in ('get', 'put', 'delete', 'patch'):
        resp = getattr(client, method)('/api/atlas/code-intel/symbol-index')
        assert resp.status_code in (404, 405)


def test_static_contract_no_shell_run_command_or_remote_git():
    text = open('agent/atlas_code_intel_service.py', 'r', encoding='utf-8').read()
    assert 'shell=True' not in text
    assert 'run_command' not in text
    assert 'git push' not in text and 'git fetch' not in text and 'git pull' not in text
