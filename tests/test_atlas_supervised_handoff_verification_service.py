import json, hashlib
from pathlib import Path
from types import SimpleNamespace

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_handoff_verification_schema import AtlasSupervisedHandoffVerificationRequest
from agent.atlas_supervised_handoff_verification_service import AtlasSupervisedHandoffVerificationService

class _Vr:
    def __init__(self, status='passed', raises=False): self.status=status; self.raises=raises
    def run_after_auto_safe_apply(self, req):
        if self.raises: raise RuntimeError('boom')
        return SimpleNamespace(status=self.status, model_dump=lambda: {'status': self.status, 'metadata': {}})
class _Ctx:
    def __init__(self, raises=False): self.raises=raises
    def refresh(self, req):
        if self.raises: raise ValueError('ctx')
        return SimpleNamespace(bundle_id='ctx1')
class _Ev:
    def __init__(self, raises=False): self.raises=raises
    def evaluate(self, req):
        if self.raises: raise ValueError('ev')
        return SimpleNamespace(model_dump=lambda: {'metadata': {'evaluator_result_id':'ev1'}, 'decision': {'decision':'allow'}})

def _setup(tmp_path):
    root=tmp_path/'ca_data'; storage=AtlasPlanPoolStorage(root); journal=AtlasJournal(root)
    item=AtlasPlanItem(item_id='i1',pool_id='p1',title='t',goal='g',status='ready',metadata={'safe_apply_handoffs':[{'handoff_id':'handoff_abc123'}]})
    storage.save_pool(AtlasPlanPool(pool_id='p1',root_goal='g',items=[item]))
    d=root/'atlas'/'safe_apply_handoffs'/'p1'; d.mkdir(parents=True)
    patch='diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@\n-old\n+new\n'
    h={'handoff_id':'handoff_abc123','status':'applied','pool_id':'p1','item_id':'i1','patch':patch,'patch_format':'unified_diff','target_files':['a.txt'],'approval_status':'approved','safe_apply_ready':True,'safe_apply_executed':True,'verification_executed':False,'metadata':{'patch_sha256':hashlib.sha256(patch.encode()).hexdigest(),'side_effects':{'safe_apply_executed':True,'verification_executed':False}}}
    (d/'handoff_abc123.json').write_text(json.dumps(h),encoding='utf-8')
    sd=root/'atlas'/'supervised_handoff_safe_apply'/'p1'; sd.mkdir(parents=True)
    sa={'pool_id':'p1','item_id':'i1','status':'applied','handoff_id':'handoff_abc123','changed_files':['a.txt'],'snapshot_id':'s1','metadata':{'side_effects':{'safe_apply_executed':True,'verification_executed':False}}}
    (sd/'safe1.json').write_text(json.dumps(sa),encoding='utf-8')
    return root,storage,journal

def test_metadata_and_events_and_failures(tmp_path):
    root,storage,journal=_setup(tmp_path)
    svc=AtlasSupervisedHandoffVerificationService(storage=storage,journal=journal,verification_service=_Vr('passed'),context_refresh_service=_Ctx(),evaluator_service=_Ev())
    r=svc.run(AtlasSupervisedHandoffVerificationRequest(pool_id='p1',item_id='i1',safe_apply_execution_id='safe1',handoff_id='handoff_abc123',run_id=''))
    assert r.status=='passed' and r.metadata['side_effects']['bounded_retry_executed'] is False
    h=json.loads((root/'atlas'/'safe_apply_handoffs'/'p1'/'handoff_abc123.json').read_text())
    assert h['verification_executed'] is True and h['verification_run_id']
    pool=storage.load_pool('p1'); item=pool.get_item('i1')
    assert item.metadata['latest_supervised_handoff_verification_result_id']==r.verification_run_id
    assert item.metadata['supervised_handoff_verification_results'][-1]['verification_run_id']==r.verification_run_id
    events=[e['event_type'] for e in journal.read_events('p1', r.verification_run_id)]
    assert 'supervised_handoff_verification_started' in events and 'supervised_handoff_verification_result_saved' in events

def test_dry_run_and_blocked_keep_verification_executed_false(tmp_path):
    root,storage,journal=_setup(tmp_path)
    svc=AtlasSupervisedHandoffVerificationService(storage=storage,journal=journal,verification_service=_Vr('passed'))
    r=svc.run(AtlasSupervisedHandoffVerificationRequest(pool_id='p1',item_id='i1',safe_apply_execution_id='safe1',handoff_id='handoff_abc123',dry_run=True))
    assert r.status=='dry_run'
    h=json.loads((root/'atlas'/'safe_apply_handoffs'/'p1'/'handoff_abc123.json').read_text())
    assert h['verification_executed'] is False

def test_failed_internal_and_context_and_evaluator_exceptions(tmp_path):
    _,storage,journal=_setup(tmp_path)
    svc=AtlasSupervisedHandoffVerificationService(storage=storage,journal=journal,verification_service=_Vr(raises=True),context_refresh_service=_Ctx(raises=True),evaluator_service=_Ev(raises=True))
    r=svc.run(AtlasSupervisedHandoffVerificationRequest(pool_id='p1',item_id='i1',safe_apply_execution_id='safe1',handoff_id='handoff_abc123',include_evaluator=True))
    assert r.status=='failed_internal'
    assert any(w.startswith('context_refresh_exception:') for w in r.warnings)
