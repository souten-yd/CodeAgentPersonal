from pathlib import Path
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(client):
    return client.post('/api/atlas/plan-pools', json={'input':'safe apply gate'}).json()


def test_execute_safe_apply_requires_approval(tmp_path):
    c=_client(tmp_path); pool=_create_pool(c); item=pool['plan_pool']['items'][0]
    r=c.post('/api/atlas/safe-apply/execute',json={'pool_id':pool['pool_id'],'item_id':item['item_id']})
    assert r.status_code==200 and r.json()['status']=='blocked' and 'approval_not_approved' in r.json()['warnings']


def test_no_batch_or_autopilot_apply_routes():
    paths={route.path for route in main.app.routes if hasattr(route,'path')}
    assert '/api/atlas/safe-apply/execute' in paths
    assert all('/safe-apply/batch' not in p for p in paths)


def test_safe_apply_execution_service_has_no_forbidden_runtime_tokens():
    src=Path('agent/atlas_safe_apply_execution_service.py').read_text(encoding='utf-8')
    for t in ['subprocess','shell=True','run_command(','TestCommandRunner(','DebugLoopRunner(','DeepResearch','deep_research_job']:
        assert t not in src
