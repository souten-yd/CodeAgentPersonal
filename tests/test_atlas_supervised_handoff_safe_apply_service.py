import json, hashlib
from pathlib import Path
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_journal import AtlasJournal
from agent.atlas_supervised_handoff_safe_apply_service import AtlasSupervisedHandoffSafeApplyService
from agent.atlas_supervised_handoff_safe_apply_schema import AtlasSupervisedHandoffSafeApplyRequest


def _setup(tmp_path):
    root=tmp_path/'ca_data'; storage=AtlasPlanPoolStorage(root); journal=AtlasJournal(root)
    pool=AtlasPlanPool(pool_id='p1',root_goal='g',items=[AtlasPlanItem(item_id='i1',pool_id='p1',title='t',goal='g',item_type='implementation',risk_level='low',status='ready',target_files=['a.txt'],metadata={'approval':{'decision':'approved'}})])
    storage.save_pool(pool)
    d=root/'atlas'/'safe_apply_handoffs'/'p1'; d.mkdir(parents=True)
    patch='diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@\n-old\n+new\n'
    h={'handoff_id':'handoff_abc123','status':'ready','pool_id':'p1','item_id':'i1','patch':patch,'patch_format':'unified_diff','target_files':['a.txt'],'approval_status':'approved','safe_apply_ready':True,'safe_apply_executed':False,'verification_executed':False,'gate_decision':{'decision':'allow'},'metadata':{'patch_sha256':hashlib.sha256(patch.encode()).hexdigest(),'side_effects':{'safe_apply_executed':False,'verification_executed':False,'bounded_retry_executed':False,'rollback_executed':False,'restore_executed':False,'debug_review_executed':False}}}
    (d/'handoff_abc123.json').write_text(json.dumps(h),encoding='utf-8')
    return root, storage, journal

def test_dry_run_validates_handoff_without_apply(tmp_path):
    root,storage,journal=_setup(tmp_path)
    svc=AtlasSupervisedHandoffSafeApplyService(storage=storage,journal=journal)
    r=svc.execute(AtlasSupervisedHandoffSafeApplyRequest(pool_id='p1',item_id='i1',handoff_id='handoff_abc123',dry_run=True))
    assert r.status=='dry_run'
    h=json.loads((root/'atlas'/'safe_apply_handoffs'/'p1'/'handoff_abc123.json').read_text())
    assert h['safe_apply_executed'] is False
