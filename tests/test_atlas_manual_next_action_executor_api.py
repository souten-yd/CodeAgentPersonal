from fastapi.testclient import TestClient
from app.server import create_app

client=TestClient(create_app())

def test_confirmation_token_preview_validation():
    r=client.post('/api/atlas/manual-next-action-executor/confirmation-token-preview',json={'orchestrator_run_id':'nextaction_1','action_id':'../bad','expected_next_action':'run_supervised_safe_apply','item_id':'i1'})
    assert r.status_code==400 and r.json()['detail']['error']=='invalid_request'

def test_confirmation_token_preview_success():
    r=client.post('/api/atlas/manual-next-action-executor/confirmation-token-preview',json={'orchestrator_run_id':'nextaction_1','action_id':'a1','expected_next_action':'run_supervised_safe_apply','item_id':'i1'})
    assert r.status_code==200 and 'MANUAL_EXECUTE:nextaction_1:a1:run_supervised_safe_apply:i1' in r.json()['confirmation_token']
