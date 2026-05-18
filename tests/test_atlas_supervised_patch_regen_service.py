import json
from pathlib import Path
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_patch_regen_service import AtlasSupervisedPatchRegenService
from agent.atlas_supervised_patch_regen_schema import AtlasPatchRegenRequest
from agent.atlas_supervised_patch_regen_client import AtlasPatchRegenNullLLMClient


def mk_pool(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path)
    item = AtlasPlanItem(pool_id='pool1', item_id='i1', title='t', description='d', item_type='implementation', goal='g', metadata={'patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=1\n+a=2\n','target_files':['a.py'],'verification':{'status':'failed','error':'AssertionError'}})
    pool = AtlasPlanPool(pool_id='pool1', root_goal='g', items=[item])
    storage.save_pool(pool)
    return storage


def test_regen_blocks_without_context_when_required(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient())
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1'))
    assert r.status == 'blocked'


def test_regen_allowed_for_deterministic_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    p = Path('ca_data/atlas/context_bundles/pool1'); p.mkdir(parents=True, exist_ok=True)
    p.joinpath('ctx1.json').write_text(json.dumps({'bundle_id':'ctx1'}), encoding='utf-8')
    pool = s.load_pool('pool1'); pool.items[0].metadata['context_bundle_id']='ctx1'; s.save_pool(pool)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=2\n+a=3\n','patch_format':'unified_diff','target_files':['a.py'],'summary':'fix','rationale':['r'],'risks':['x'],'verification_suggestions':[],'manual_review_required':True,'approval_required':True})
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1'))
    assert r.candidate.status == 'proposal_ready'
    assert r.candidate.approval_status == 'pending'
    assert r.candidate.safe_apply_ready is False

