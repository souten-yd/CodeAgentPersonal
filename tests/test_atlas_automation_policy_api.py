from pathlib import Path
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def test_automation_decide_api_does_not_execute_safe_apply(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'automation', 'project_path': str(tmp_path)}).json()['plan_pool']
    item = created['items'][0]
    item.setdefault('metadata', {})
    item['metadata'].update({'approval': {'decision': 'approved'}, 'action_type': 'update', 'patch': 'x', 'source_proposal_id': 'pp1'})
    item['risk_level'] = 'low'; item['item_type'] = 'implementation'; item['target_files'] = ['a.txt']
    candidates = [
        Path(tmp_path) / 'atlas' / 'plan_pools' / f"{created['pool_id']}.json",
        Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / created['pool_id'] / 'plan_pool.json',
    ]
    for p in candidates:
        if p.exists():
            data = __import__('json').loads(p.read_text())
            data['project_path'] = str(tmp_path)
            data['items'][0] = item
            p.write_text(__import__('json').dumps(data))
    res = c.post('/api/atlas/automation/decide', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'preset_id': 'guarded_low_risk', 'phase': 'pre_safe_apply', 'workspace_id': 'default'}).json()
    assert res['decision']['decision'] == 'allow'
    events = c.get(f"/api/atlas/pipeline/events/{created['pool_id']}/run_missing").json()
    assert all(e.get('event_type') not in {'safe_apply_manual_started', 'safe_apply_auto_started'} for e in events.get('events', []))


def test_no_auto_routes_added():
    src = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    assert '/api/atlas/automation/decide' not in src or '/automation/decide' in src
    assert '/api/atlas/automation/run' not in src
    assert '/api/task/' not in src
    assert '/api/agent/' not in src
