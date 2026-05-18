import json
from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_regen_from_recommendation_schema import AtlasPatchRegenFromRecommendationRequest
from agent.atlas_patch_regen_from_recommendation_service import AtlasPatchRegenFromRecommendationService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_patch_regen_schema import AtlasPatchProposalCandidate, AtlasPatchRegenInputPacket, AtlasPatchRegenResult


class FakePatchRegen:
    def __init__(self):
        self.calls = []
    def regenerate(self, req):
        self.calls.append(req)
        candidate = AtlasPatchProposalCandidate(proposal_id="proposal_1", status="proposal_ready", patch="diff --git a/src/a.py b/src/a.py", target_files=["src/a.py"], summary="fix")
        packet = AtlasPatchRegenInputPacket(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, policy_id=req.policy_id, target_files=req.target_files, original_patch=req.original_patch)
        return AtlasPatchRegenResult(pool_id=req.pool_id, item_id=req.item_id, run_id=req.run_id, regen_run_id="regen_fake1", policy_id=req.policy_id, status="proposal_ready", candidate=candidate, input_packet=packet, metadata={"side_effects":{"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False}})


def setup_env(tmp_path, monkeypatch, *, rec_status="recommendation_ready", payload=True, target_files=None, original_patch="diff --git a/src/a.py b/src/a.py", prior=False):
    monkeypatch.chdir(tmp_path)
    storage = AtlasPlanPoolStorage(tmp_path)
    item = AtlasPlanItem(pool_id="p1", item_id="i1", title="t", goal="g", metadata={
        "patch": "keep_patch", "safe_apply": {"keep": True}, "auto_safe_apply": {"keep": True},
        "patch_regen_recommendations": [{"recommendation_run_id":"regenrec_abc123","handoff_id":"handoff_abc123"}],
        "safe_apply_handoffs": [{"handoff_id":"handoff_abc123"}],
    })
    if prior:
        item.metadata["patch_regen_from_recommendation_results"] = [{"recommendation_run_id":"regenrec_abc123","status":"patch_regen_created"}]
    storage.save_pool(AtlasPlanPool(pool_id="p1", root_goal="g", items=[item]))
    rec_payload = None
    if payload:
        rec_payload = {"pool_id":"p1","item_id":"i1","context_bundle_id":"","retry_run_id":"","evaluator_result_id":"","verification_result":{"error":"AssertionError test failed"},"bounded_retry_result":{"status":"exhausted"},"failure_stop_suggestion":{"stop":True},"original_patch":original_patch,"changed_files":["src/a.py"],"target_files":target_files or ["src/a.py"],"metadata":{}}
    rec = {"pool_id":"p1","item_id":"i1","run_id":"run1","handoff_id":"handoff_abc123","safe_apply_execution_id":"safehandoff_abc123","verification_run_id":"verifyhandoff_abc123","supervised_retry_run_id":"retryhandoff_abc123","recommendation_run_id":"regenrec_abc123","policy_id":"patch_regen_recommendation_v1","patch_regen_policy_id":"supervised_patch_regen_v1","status":rec_status,"recommended_payload":rec_payload,"eligibility":{"retry_reason":"deterministic_test_failure_or_code_error","deterministic_failure_detected":True},"warnings":[],"errors":[],"metadata":{"auto_execute_patch_regen":False,"side_effects":{"patch_regeneration_executed":False,"safe_apply_executed":False,"verification_executed":False}}}
    root = Path("ca_data/atlas/patch_regen_recommendations/p1"); root.mkdir(parents=True, exist_ok=True)
    root.joinpath("regenrec_abc123.json").write_text(json.dumps(rec), encoding="utf-8")
    hroot = Path("ca_data/atlas/safe_apply_handoffs/p1"); hroot.mkdir(parents=True, exist_ok=True)
    hroot.joinpath("handoff_abc123.json").write_text(json.dumps({"handoff_id":"handoff_abc123","metadata":{}}), encoding="utf-8")
    return storage


def run_service(storage, fake, **kw):
    svc = AtlasPatchRegenFromRecommendationService(storage=storage, journal=AtlasJournal("ca_data"), patch_regen_service=fake)
    req = AtlasPatchRegenFromRecommendationRequest(pool_id="p1", item_id="i1", recommendation_run_id="regenrec_abc123", reviewer="manual", reason="test", **kw)
    return svc.run(req)


def test_dry_run_validates_without_calling_patch_regen(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch); fake = FakePatchRegen()
    result = run_service(storage, fake, dry_run=True)
    assert result.status == "dry_run"
    assert fake.calls == []


def test_blocks_non_ready_recommendation(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch, rec_status="blocked"); fake = FakePatchRegen()
    result = run_service(storage, fake)
    assert result.status == "blocked"
    assert "recommendation_not_ready" in result.errors
    assert fake.calls == []


def test_blocks_missing_recommended_payload(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch, payload=False); fake = FakePatchRegen()
    result = run_service(storage, fake)
    assert result.status == "blocked"
    assert "recommended_payload_missing" in result.errors


def test_blocks_prior_execution_when_reexecute_false(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch, prior=True); fake = FakePatchRegen()
    result = run_service(storage, fake)
    assert result.status == "blocked"
    assert "prior_patch_regen_execution_exists" in result.errors


def test_executes_patch_regen_from_valid_recommendation(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch); fake = FakePatchRegen()
    result = run_service(storage, fake)
    assert result.status == "patch_regen_created"
    assert result.patch_regen_result_id == "regen_fake1"
    assert fake.calls[0].metadata["source"] == "patch_regen_from_recommendation"
    assert fake.calls[0].dry_run is False


def test_candidate_requires_manual_approval(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch); fake = FakePatchRegen()
    result = run_service(storage, fake)
    candidate = result.patch_regen_result["candidate"]
    assert candidate["approval_required"] is True
    assert candidate["approval_status"] == "pending"
    assert candidate["safe_apply_ready"] is False


def test_does_not_call_safe_apply_verification_retry(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch); fake = FakePatchRegen()
    result = run_service(storage, fake)
    assert result.metadata["side_effects"] == {"patch_regeneration_executed": True, "safe_apply_executed": False, "verification_executed": False, "bounded_retry_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "auto_approval_executed": False}
    events = "\n".join(p.read_text() for p in Path("ca_data/atlas/workspaces/default/plan_pools/p1").glob("pipeline_runs/*/events.ndjson"))
    assert "safe_apply_auto_started" not in events
    assert "auto_verification_started" not in events
    assert "bounded_retry_started" not in events


def test_target_files_revalidated(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch, target_files=["../x"]); fake = FakePatchRegen()
    result = run_service(storage, fake)
    assert result.status == "blocked"
    assert "target_files_unsafe" in result.errors


def test_original_patch_missing_blocks(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch, original_patch=""); fake = FakePatchRegen()
    result = run_service(storage, fake)
    assert result.status == "blocked"
    assert "original_patch_missing" in result.errors


def test_result_json_and_md_saved(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch, original_patch="SECRET_FULL_PATCH_SHOULD_NOT_APPEAR"); fake = FakePatchRegen()
    result = run_service(storage, fake)
    root = Path("ca_data/atlas/patch_regen_from_recommendations/p1")
    assert root.joinpath(f"{result.recommendation_exec_id}.json").exists()
    md = root.joinpath(f"{result.recommendation_exec_id}.md").read_text()
    assert "SECRET_FULL_PATCH_SHOULD_NOT_APPEAR" not in md
    assert "diff --git a/src/a.py b/src/a.py" not in md


def test_handoff_metadata_updated(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch); fake = FakePatchRegen()
    result = run_service(storage, fake)
    handoff = json.loads(Path("ca_data/atlas/safe_apply_handoffs/p1/handoff_abc123.json").read_text())
    assert handoff["metadata"]["last_patch_regen_result_id"] == result.patch_regen_result_id
    assert handoff["metadata"]["patch_regen_from_recommendation_results"]


def test_item_metadata_updated(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch); fake = FakePatchRegen()
    result = run_service(storage, fake)
    item = storage.load_pool("p1").get_item("i1")
    assert item.metadata["latest_patch_regen_from_recommendation_exec_id"] == result.recommendation_exec_id
    assert item.metadata["patch_regen_from_recommendation_results"]
    assert item.metadata["patch_regen_recommendations"][0]["patch_regen_executed"] is True


def test_item_patch_safe_apply_not_overwritten(tmp_path, monkeypatch):
    storage = setup_env(tmp_path, monkeypatch); fake = FakePatchRegen()
    before = storage.load_pool("p1").get_item("i1").metadata.copy()
    run_service(storage, fake)
    after = storage.load_pool("p1").get_item("i1").metadata
    assert after["patch"] == before["patch"]
    assert after["safe_apply"] == before["safe_apply"]
    assert after["auto_safe_apply"] == before["auto_safe_apply"]
