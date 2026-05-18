import json, hashlib
from pathlib import Path
from types import SimpleNamespace
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_handoff_retry_schema import AtlasSupervisedHandoffRetryRequest
from agent.atlas_supervised_handoff_retry_service import AtlasSupervisedHandoffRetryService

class _BR:
    def run(self, req):
        return SimpleNamespace(status='recovered', retry_run_id='retry_1', final_verification_status='passed', model_dump=lambda:{'status':'recovered'})

def test_dry_run_classifies_without_retry(tmp_path):
    root=tmp_path/'ca_data'; st=AtlasPlanPoolStorage(root); j=AtlasJournal(root)
    it=AtlasPlanItem(item_id='i1',pool_id='p1',title='t',goal='g',status='ready',metadata={}); st.save_pool(AtlasPlanPool(pool_id='p1',root_goal='g',items=[it]))
    (root/'atlas'/'supervised_handoff_verification'/'p1').mkdir(parents=True); (root/'atlas'/'supervised_handoff_safe_apply'/'p1').mkdir(parents=True); (root/'atlas'/'safe_apply_handoffs'/'p1').mkdir(parents=True)
    (root/'atlas'/'supervised_handoff_verification'/'p1'/'verifyhandoff_1.json').write_text(json.dumps({'status':'failed','verification_result':{'status':'failed'},'changed_files':['a'],'handoff_id':'handoff_1'}))
    (root/'atlas'/'supervised_handoff_safe_apply'/'p1'/'safehandoff_1.json').write_text(json.dumps({'status':'applied','handoff_id':'handoff_1'}))
    (root/'atlas'/'safe_apply_handoffs'/'p1'/'handoff_1.json').write_text(json.dumps({'handoff_id':'handoff_1','metadata':{}}))
    svc=AtlasSupervisedHandoffRetryService(storage=st,journal=j,bounded_retry_service=_BR())
    r=svc.run(AtlasSupervisedHandoffRetryRequest(pool_id='p1',item_id='i1',safe_apply_execution_id='safehandoff_1',verification_run_id='verifyhandoff_1',handoff_id='handoff_1',dry_run=True))
    assert r.status=='dry_run'
