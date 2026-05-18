import json
from pathlib import Path
from agent.atlas_patch_candidate_approval_schema import AtlasPatchCandidateApprovalRequest
from agent.atlas_patch_candidate_approval_service import AtlasPatchCandidateApprovalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem


def _seed(tmp_path):
    storage = AtlasPlanPoolStorage(Path("ca_data"))
    pool = AtlasPlanPool(pool_id='pool1', root_goal='g', items=[AtlasPlanItem(pool_id='pool1', item_id='i1', title='t', item_type='implementation', goal='g', risk_level='low', target_files=['a.py'], metadata={'patch':'keep','safe_apply':{'x':1},'patch_regen_candidates':[{'regen_run_id':'regen_1','proposal_id':'prop1','status':'proposal_ready','approval_status':'pending','safe_apply_ready':False,'target_files':['a.py']}]})])
    storage.save_pool(pool)
    rr = Path('ca_data')/'atlas'/'patch_regen'/'pool1'; rr.mkdir(parents=True, exist_ok=True)
    rr.joinpath('regen_1.json').write_text(json.dumps({'status':'proposal_ready','candidate':{'proposal_id':'prop1','status':'proposal_ready','patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-old\n+new\n','patch_format':'unified_diff','target_files':['a.py'],'warnings':[],'errors':[]}}))
    return storage


def test_approve_valid_candidate_creates_handoff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s=_seed(tmp_path)
    svc=AtlasPatchCandidateApprovalService(storage=s)
    class _D:
        decision='allow'; reasons=[]; metadata={'risk_level':'low'}
    svc.gate=type('G',(),{'decide_pre_safe_apply':lambda *a,**k:_D()})()
    res=svc.decide(AtlasPatchCandidateApprovalRequest(pool_id='pool1', item_id='i1', regen_run_id='regen_1', decision='approve'))
    assert res.status=='approved' and res.handoff and res.handoff.safe_apply_ready and not res.handoff.safe_apply_executed


def test_reject_candidate_updates_metadata_without_handoff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); s=_seed(tmp_path)
    res=AtlasPatchCandidateApprovalService(storage=s).decide(AtlasPatchCandidateApprovalRequest(pool_id='pool1', item_id='i1', regen_run_id='regen_1', decision='reject'))
    assert res.status=='rejected' and res.handoff is None
