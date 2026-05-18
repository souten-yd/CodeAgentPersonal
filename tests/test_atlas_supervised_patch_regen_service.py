import json
from pathlib import Path
import pytest
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_patch_regen_service import AtlasSupervisedPatchRegenService
from agent.atlas_supervised_patch_regen_schema import AtlasPatchRegenRequest
from agent.atlas_supervised_patch_regen_client import AtlasPatchRegenNullLLMClient


def mk_pool(tmp_path, with_ctx=True):
    storage = AtlasPlanPoolStorage(tmp_path)
    item = AtlasPlanItem(pool_id='pool1', item_id='i1', title='t', description='d', item_type='implementation', goal='g', metadata={'patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=1\n+a=2\n','target_files':['a.py'],'verification':{'status':'failed'}})
    if with_ctx:
        item.metadata['context_bundle_id']='ctx_ok'
        d = Path(tmp_path)/'ca_data/atlas/context_bundles/pool1'
        d.mkdir(parents=True, exist_ok=True)
        d.joinpath('ctx_ok.json').write_text(json.dumps({'bundle_id':'ctx_ok'}), encoding='utf-8')
    pool = AtlasPlanPool(pool_id='pool1', root_goal='g', items=[item])
    storage.save_pool(pool)
    return storage


def test_regen_proposal_ready_and_metadata(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=2\n+a=3\n','patch_format':'unified_diff','target_files':['a.py'],'summary':'fix'})
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', context_bundle_id='ctx_ok'))
    assert r.candidate.status == 'proposal_ready'
    assert r.candidate.safe_apply_ready is False
    assert r.metadata['side_effects']['safe_apply_executed'] is False


def test_regen_blocks_unexpected_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@\n-x=1\n+x=2\n','patch_format':'unified_diff','target_files':['b.py'],'summary':'fix'})
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1'))
    assert r.status == 'blocked'


def test_secret_like_goes_manual_and_redacted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=2\n+token=sk-xxx\n','patch_format':'unified_diff','target_files':['a.py'],'summary':'fix'})
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1'))
    assert r.candidate.status == 'manual_required'
    assert 'secret_like_content_detected' in r.candidate.warnings
    md = Path('ca_data/atlas/patch_regen/pool1').joinpath(f'{r.regen_run_id}.md').read_text(encoding='utf-8')
    assert 'sk-xxx' not in md


def test_failed_result_saved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned='{}'))
    with pytest.raises(Exception):
        svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='missing'))
    assert list(Path('ca_data/atlas/patch_regen/pool1').glob('regen_*.json'))
