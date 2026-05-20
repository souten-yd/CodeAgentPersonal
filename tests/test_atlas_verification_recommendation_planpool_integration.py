from fastapi.testclient import TestClient
from app.server import create_app
import app.api.atlas_pipeline as mod

def test_planpool_gets_verification_recommendation(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=str(tmp_path)
    c=TestClient(app)
    r=c.post('/api/atlas/plan-pools', json={'input':'g','project_path':str(tmp_path),'enable_repo_context':True})
    md=r.json()['plan_pool']['metadata']
    assert 'verification_recommendation' in md
    v=md['verification_recommendation']
    assert len(v['impacted_files'])<=30 and len(v['related_tests'])<=20 and len(v['recommended_commands'])<=5 and len(v['manual_verification_steps'])<=10
    assert v['advisory_only'] is True and v['executed'] is False and v['auto_verification_triggered'] is False and v['auto_test_execution_triggered'] is False and v['commands_are_suggestions_only'] is True

def test_disable_repo_context_no_active(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=str(tmp_path)
    c=TestClient(app)
    r=c.post('/api/atlas/plan-pools', json={'input':'g','project_path':str(tmp_path),'enable_repo_context':False})
    md=r.json()['plan_pool']['metadata']
    assert 'verification_recommendation' not in md or md['verification_recommendation'].get('status') in {'missing','inactive','failed'}

def test_plan_payload_path(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=str(tmp_path)
    c=TestClient(app)
    payload={'items':[{'item_id':'i1','title':'t','description':'d'}]}
    r=c.post('/api/atlas/plan-pools', json={'input':'g','project_path':str(tmp_path),'enable_repo_context':True,'plan_payload':payload})
    assert 'verification_recommendation' in r.json()['plan_pool']['metadata']

def test_service_failure_non_blocking(tmp_path, monkeypatch):
    class Bad:
        def __init__(self, data_root): pass
        def recommend(self, req): raise RuntimeError('x')
    monkeypatch.setattr(mod, 'AtlasVerificationRecommendationService', Bad)
    app=create_app(); app.state.atlas_ca_data_root=str(tmp_path)
    c=TestClient(app)
    r=c.post('/api/atlas/plan-pools', json={'input':'g','project_path':str(tmp_path),'enable_repo_context':True})
    assert r.status_code==200
    assert r.json()['plan_pool']['metadata']['verification_recommendation']['status']=='failed'
