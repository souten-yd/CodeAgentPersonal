import json
from pathlib import Path
import pytest
from agent.atlas_plan_pool_schema import AtlasPlanPool, AtlasPlanItem
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_patch_regen_service import AtlasSupervisedPatchRegenService
from agent.atlas_supervised_patch_regen_schema import AtlasPatchRegenRequest
from agent.atlas_supervised_patch_regen_client import AtlasPatchRegenNullLLMClient
from agent.atlas_journal import AtlasJournal


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
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', context_bundle_id='ctx_ok', verification_result={"error": "AssertionError test failed"}))
    assert r.candidate.status == 'proposal_ready'
    assert r.candidate.safe_apply_ready is False
    assert r.metadata['side_effects']['safe_apply_executed'] is False


def test_regen_blocks_unexpected_target(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@\n-x=1\n+x=2\n','patch_format':'unified_diff','target_files':['b.py'],'summary':'fix'})
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', verification_result={"error": "AssertionError"}))
    assert r.status == 'blocked'


def test_secret_like_goes_manual_and_redacted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=2\n+token=sk-xxx\n','patch_format':'unified_diff','target_files':['a.py'],'summary':'fix'})
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', verification_result={"error": "AssertionError"}))
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


def test_transient_failure_not_regeneratable_and_no_llm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned='{"status":"proposal_ready"}'))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', verification_result={"error": "timeout in runner unavailable"}))
    assert r.status == "not_regeneratable"
    assert r.raw_llm_output == ""


def test_bounded_retry_recovered_not_regeneratable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned='{"status":"proposal_ready"}'))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', bounded_retry_result={"status": "recovered"}))
    assert r.status == "not_regeneratable"


def test_original_patch_missing_not_regeneratable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage = AtlasPlanPoolStorage(tmp_path)
    item = AtlasPlanItem(pool_id='pool1', item_id='i1', title='t', description='d', item_type='implementation', goal='g', metadata={'target_files':['a.py'], 'verification': {'error': 'AssertionError'}})
    d = Path(tmp_path)/'ca_data/atlas/context_bundles/pool1'; d.mkdir(parents=True, exist_ok=True); d.joinpath('ctx_ok.json').write_text(json.dumps({'bundle_id':'ctx_ok'}), encoding='utf-8')
    item.metadata['context_bundle_id'] = 'ctx_ok'
    storage.save_pool(AtlasPlanPool(pool_id='pool1', root_goal='g', items=[item]))
    svc = AtlasSupervisedPatchRegenService(storage=storage, llm_client=AtlasPatchRegenNullLLMClient(canned='{"status":"proposal_ready"}'))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1'))
    assert r.status == "not_regeneratable"


def test_prompt_truncation_keeps_rules_and_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=2\n+a=3\n','patch_format':'unified_diff','target_files':['a.py'],'summary':'fix'})
    svc = AtlasSupervisedPatchRegenService(storage=s, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', verification_result={"error": "AssertionError"}, max_prompt_chars=500))
    assert "## Non-negotiable rules" in r.prompt_preview
    assert "## Required JSON schema" in r.prompt_preview
    assert r.metadata["prompt_truncated"] is True
    assert "prompt_context_truncated" in r.input_packet.warnings


def test_metadata_and_journal_events_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = mk_pool(tmp_path)
    raw = json.dumps({'status':'proposal_ready','patch':'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@\n-a=2\n+a=3\n','patch_format':'unified_diff','target_files':['a.py'],'summary':'fix'})
    journal = AtlasJournal("ca_data")
    svc = AtlasSupervisedPatchRegenService(storage=s, journal=journal, llm_client=AtlasPatchRegenNullLLMClient(canned=raw))
    r = svc.regenerate(AtlasPatchRegenRequest(pool_id='pool1', item_id='i1', run_id='run1', verification_result={"error":"AssertionError"}))
    assert "input_resolution_sources" in r.metadata
    assert "candidate_validation_errors" in r.metadata
    events = Path("ca_data/atlas/workspaces/default/plan_pools/pool1/pipeline_runs/run1/events.ndjson")
    assert events.exists()
    assert "patch_regen_started" in events.read_text(encoding="utf-8")
