from pathlib import Path
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def test_route_and_ui_contracts_present():
    api = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    js = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    html = Path('ui.html').read_text(encoding='utf-8')
    assert '/automation/safe-apply-one' in api
    assert 'autoSafeApplyOne(payload)' in js
    assert 'Run gated auto safe_apply for this item' in html
    assert 'runAutoSafeApplyOne' in dash
    for forbidden in ('/api/task/', '/api/agent/', '/automation/run', 'Apply all', 'Batch'):
        assert forbidden not in (api + js + dash)


def test_manual_only_preset_blocks_auto_safe_apply(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'x'}).json()['plan_pool']
    item = created['items'][0]
    res = c.post('/api/atlas/automation/safe-apply-one', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'preset_id': 'manual_only'}).json()
    assert res['status'] in {'blocked', 'skipped'}
