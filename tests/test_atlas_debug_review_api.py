from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_debug_review_schema import AtlasDebugReviewRequest


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(client):
    body = client.post('/api/atlas/plan-pools', json={'input': 'debug review'}).json()
    return body


def test_debug_review_requires_failed_verification(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    res = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'})
    assert res.status_code == 200
    assert res.json()['status'] == 'blocked'
    assert 'verification_not_failed' in res.json()['warnings']


def test_debug_review_schema_has_no_patch_or_command_fields():
    fields = set(AtlasDebugReviewRequest.model_fields.keys())
    for forbidden in ('patch', 'command', 'shell', 'apply'):
        assert forbidden not in fields


def test_debug_review_service_has_no_forbidden_tokens():
    source = Path('agent/atlas_debug_review_service.py').read_text(encoding='utf-8')
    for forbidden in ('subprocess', 'shell=True', 'safe_apply(', 'execute_safe_apply', 'TestCommandRunner(', 'DeepResearch', 'run_command(', 'unlink('):
        assert forbidden not in source


def test_no_batch_debug_review_route(tmp_path):
    c = _client(tmp_path)
    assert c.post('/api/atlas/debug-review/batch', json={}).status_code in {404, 405}
