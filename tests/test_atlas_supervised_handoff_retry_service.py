import json
from pathlib import Path
from types import SimpleNamespace
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_handoff_retry_schema import AtlasSupervisedHandoffRetryRequest
from agent.atlas_supervised_handoff_retry_service import AtlasSupervisedHandoffRetryService

class _BR:
    def __init__(self,status='recovered'): self.status=status
    def run(self, req):
        if self.status=='boom': raise RuntimeError('x')
        return SimpleNamespace(status=self.status, retry_run_id='retry_1', final_verification_status='passed' if self.status=='recovered' else 'failed', model_dump=lambda:{'status':self.status})

def _setup(tmp_path, ver=None, safe=None, hand=None, item_meta=None):
    root=tmp_path/'ca_data'; st=AtlasPlanPoolStorage(root); j=AtlasJournal(root)
    it=AtlasPlanItem(item_id='i1',pool_id='p1',title='t',goal='g',status='ready',metadata=item_meta or {'safe_apply_handoffs':[{'safe_apply_execution_id':'safehandoff_1'}]})
    st.save_pool(AtlasPlanPool(pool_id='p1',root_goal='g',items=[it]))
    (root/'atlas'/'supervised_handoff_verification'/'p1').mkdir(parents=True); (root/'atlas'/'supervised_handoff_safe_apply'/'p1').mkdir(parents=True); (root/'atlas'/'safe_apply_handoffs'/'p1').mkdir(parents=True)
    v=ver or {'pool_id':'p1','item_id':'i1','status':'failed','verification_result':{'status':'failed','stderr_tail':'timeout'},'safe_apply_execution_id':'safehandoff_1','changed_files':['a'],'handoff_id':'handoff_1','metadata':{'side_effects':{'safe_apply_rerun_executed':False,'bounded_retry_executed':False,'rollback_executed':False,'restore_executed':False,'patch_regeneration_executed':False}}}
    s=safe or {'pool_id':'p1','item_id':'i1','status':'applied','handoff_id':'handoff_1','safe_apply_result':{'ok':1},'changed_files':['a'],'metadata':{'side_effects':{'safe_apply_executed':True,'verification_executed':False}}}
    h=hand or {'pool_id':'p1','item_id':'i1','handoff_id':'handoff_1','safe_apply_executed':True,'safe_apply_execution_id':'safehandoff_1','verification_run_id':'verifyhandoff_1','verification_status':'failed','metadata':{}}
    (root/'atlas'/'supervised_handoff_verification'/'p1'/'verifyhandoff_1.json').write_text(json.dumps(v))
    (root/'atlas'/'supervised_handoff_safe_apply'/'p1'/'safehandoff_1.json').write_text(json.dumps(s))
    (root/'atlas'/'safe_apply_handoffs'/'p1'/'handoff_1.json').write_text(json.dumps(h))
    return st,j

def _req(): return AtlasSupervisedHandoffRetryRequest(pool_id='p1',item_id='i1',safe_apply_execution_id='safehandoff_1',verification_run_id='verifyhandoff_1',handoff_id='handoff_1',dry_run=False)

def test_blocks_when_verification_result_pool_item_mismatch(tmp_path):
    st,j=_setup(tmp_path,ver={'pool_id':'p2','item_id':'i2','verification_result':{'status':'failed','stderr_tail':'timeout'},'metadata':{'side_effects':{}},'handoff_id':'handoff_1'})
    r=AtlasSupervisedHandoffRetryService(storage=st,journal=j,bounded_retry_service=_BR()).run(_req())
    assert r.status=='blocked'

def test_exhausted_sets_patch_regen_recommended(tmp_path):
    st,j=_setup(tmp_path)
    r=AtlasSupervisedHandoffRetryService(storage=st,journal=j,bounded_retry_service=_BR('exhausted')).run(_req())
    assert r.metadata['patch_regen_recommended'] is True

def test_recovered_sets_recovered_by_bounded_retry(tmp_path):
    st,j=_setup(tmp_path)
    r=AtlasSupervisedHandoffRetryService(storage=st,journal=j,bounded_retry_service=_BR('recovered')).run(_req())
    assert r.status=='recovered'

def test_default_bounded_retry_service_is_constructed(tmp_path):
    st,j=_setup(tmp_path)
    s=AtlasSupervisedHandoffRetryService(storage=st,journal=j)
    assert s.bounded_retry_service is not None

def test_bounded_retry_exception_saves_failed_internal_result(tmp_path):
    st,j=_setup(tmp_path)
    r=AtlasSupervisedHandoffRetryService(storage=st,journal=j,bounded_retry_service=_BR('boom')).run(_req())
    assert r.status=='failed_internal'
