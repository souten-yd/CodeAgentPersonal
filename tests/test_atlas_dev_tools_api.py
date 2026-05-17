from fastapi.testclient import TestClient

import main


def test_dev_tools_endpoints_and_project_path_required(tmp_path):
    client = TestClient(main.app)
    r = client.post('/api/atlas/dev-tools/git-status', json={})
    assert r.status_code == 422

    repo = tmp_path / 'repo'
    repo.mkdir()
    import subprocess
    subprocess.run(['git', 'init'], cwd=repo, check=True, capture_output=True)
    (repo/'a.py').write_text('def f():\n    pass\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, check=True, capture_output=True)

    ok = client.post('/api/atlas/dev-tools/project-tree', json={'project_path': str(repo)})
    assert ok.status_code == 200
    ol = client.post('/api/atlas/dev-tools/file-outline', json={'project_path': str(repo), 'relative_path': 'a.py'})
    assert ol.status_code == 200
