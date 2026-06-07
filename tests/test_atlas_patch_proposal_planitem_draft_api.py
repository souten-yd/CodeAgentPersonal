from pathlib import Path

from fastapi.testclient import TestClient

import main
from tests.test_atlas_patch_proposal_api import _create_pool as _seed_patch_pool


API = Path("app/api/atlas_pipeline.py")
SERVICE = Path("agent/atlas_patch_proposal_planitem_service.py")
API_JS = Path("web/js/atlas_pipeline_api.js")
DASH_JS = Path("web/js/atlas_dashboard.js")


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _seed_pool(client):
    pool = _seed_patch_pool(client)["plan_pool"]
    item = pool["items"][0]
    return pool["pool_id"], item["item_id"]


def _set_patch(client, pool_id, item_id, status="approved", approval=True, target_files=None, risk="low"):
    pool = client.get(f"/api/atlas/plan-pools/{pool_id}").json()["plan_pool"]
    item = next(i for i in pool["items"] if i["item_id"] == item_id)
    item.setdefault("metadata", {})["patch_proposal"] = {
        "status": status, "proposal_id": "p1", "summary": "s", "proposed_fix": "f", "risk_level": risk,
        "target_files": target_files if target_files is not None else ["agent/x.py"], "suggested_changes": [{"a": 1}],
        "verification_plan": ["v"], "rollback_plan": ["r"],
        "metadata": {
            "patch_generation": {
                "run_id": "r1",
                "state": "succeeded",
                "outcome": "success",
                "patch_content_available": True,
            }
        },
    }
    item["metadata"]["patch_generation"] = {
        "run_id": "r1",
        "state": "succeeded",
        "outcome": "success",
        "patch_content_available": True,
    }
    if approval:
        item["metadata"]["patch_proposal_approval"] = {"decision": "approved"}
    plan_path = Path(tmp_path := main.app.state.atlas_ca_data_dir) / "atlas" / "workspaces" / "default" / "plan_pools" / pool_id / "plan_pool.json"
    plan_path.write_text(__import__('json').dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')


def test_planitem_draft_requires_approved_patch_proposal(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id, status="proposed")
    r = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id})
    assert r.json()["status"] == "blocked" and "patch_proposal_not_approved" in r.json()["warnings"]


def test_planitem_draft_requires_approval_decision(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id, approval=False)
    r = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id})
    assert r.json()["status"] == "blocked" and "patch_proposal_approval_not_approved" in r.json()["warnings"]


def test_planitem_draft_creates_approval_required_planitem(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    body = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    d = body["draft_item"]; assert body["status"] == "created"; assert d["status"] == "approval_required"; assert d["requires_user_confirmation"] is True
    assert d["metadata"]["source"] == "patch_proposal" and d["metadata"]["manual_safe_apply_required"] is True and d["metadata"]["auto_execute"] is False


def test_planitem_draft_does_not_mark_safe_apply_approved(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    b = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    assert "approval" not in (b["draft_item"]["metadata"] or {})


def test_planitem_draft_blocks_duplicate_creation(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id})
    b = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    assert b["status"] == "blocked" and "draft_already_exists" in b["warnings"]


def test_planitem_draft_blocks_unsafe_target_files(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id, target_files=["../x"])
    b = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    assert b["status"] == "blocked" and "unsafe_target_files" in b["warnings"]


def test_planitem_draft_record_saved_and_event(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    b = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id, "run_id": "r1"}).json()
    md = Path(b["metadata"]["draft_md_path"]).read_text(encoding="utf-8")
    assert "No patch was applied." in md and "No safe_apply was run." in md and "No verification was run." in md and "requires PlanItem approval" in md


def test_planitem_draft_response_includes_recovery_orchestration_continuation(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    b = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    assert isinstance(b["recovery_summary"], dict) and isinstance(b["orchestration_summary"], dict) and isinstance(b["continuation_prompt"], str)


def test_planitem_draft_does_not_execute_anything():
    txt = SERVICE.read_text(encoding="utf-8")
    for f in ["safe_apply(", "execute_safe_apply", "runVerification", "TestCommandRunner(", "DebugLoopRunner(", "ImplementationExecutor", "subprocess", "shell=True", "run_command("]:
        assert f not in txt


def test_no_planitem_draft_batch_or_apply_routes():
    src = API.read_text(encoding="utf-8")
    assert '/patch-proposals/planitem-draft' in src
    assert '/patch-proposals/planitem-draft/batch' not in src and '/patch-proposals/apply' not in src


def test_ui_contract_for_draft_controls():
    api = API_JS.read_text(encoding='utf-8'); dash = DASH_JS.read_text(encoding='utf-8')
    assert 'createPatchProposalPlanItemDraft(payload)' in api
    assert 'createPatchProposalPlanItemDraft(itemId)' in dash
    assert 'Create manual safe_apply PlanItem Draft' in dash
    assert 'No PlanItem approval is performed automatically.' in dash
    for forbidden in ['Apply patch', 'Auto apply', 'Safe apply now', 'Re-run verification', 'Continue autopilot', 'Run command']:
        assert forbidden not in (api + dash)


def test_planitem_draft_appears_in_approval_required_items(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    body = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    draft_item_id = body["draft_item"]["draft_item_id"]
    approvals = c.get(f"/api/atlas/approvals/pools/{pool_id}").json()
    assert any(it["item_id"] == draft_item_id for it in approvals["approval_required_items"])
    assert approvals["pending_count"] >= 1


def test_planitem_draft_can_be_approved_by_existing_approval_gate(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    body = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    draft_item_id = body["draft_item"]["draft_item_id"]
    c.post('/api/atlas/approvals/decide', json={"pool_id": pool_id, "item_id": draft_item_id, "decision": "approved"})
    pool = c.get(f"/api/atlas/plan-pools/{pool_id}").json()["plan_pool"]
    draft = next(it for it in pool["items"] if it["item_id"] == draft_item_id)
    assert draft["metadata"]["approval"]["decision"] == "approved"
    assert draft["status"] in {"ready", "approved", "completed"}


def test_approved_draft_becomes_safe_apply_candidate(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    body = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    draft_item_id = body["draft_item"]["draft_item_id"]
    c.post('/api/atlas/approvals/decide', json={"pool_id": pool_id, "item_id": draft_item_id, "decision": "approved"})
    approvals = c.get(f"/api/atlas/approvals/pools/{pool_id}").json()
    assert any(it["item_id"] == draft_item_id for it in approvals["safe_apply_candidate_items"])


def test_approved_draft_safe_apply_without_executor_is_blocked(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    body = c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id}).json()
    draft_item_id = body["draft_item"]["draft_item_id"]
    c.post('/api/atlas/approvals/decide', json={"pool_id": pool_id, "item_id": draft_item_id, "decision": "approved"})
    for key in ("atlas_safe_apply_adapter", "atlas_implementation_executor"):
        if hasattr(main.app.state, key):
            delattr(main.app.state, key)
    result = c.post('/api/atlas/safe-apply/execute', json={"pool_id": pool_id, "item_id": draft_item_id, "run_id": "run_draft_1"}).json()
    assert result["status"] == "blocked"
    assert "safe_apply_executor_unavailable" in result["warnings"]
    pool = c.get(f"/api/atlas/plan-pools/{pool_id}").json()["plan_pool"]
    draft = next(it for it in pool["items"] if it["item_id"] == draft_item_id)
    assert draft["status"] != "completed"


def test_planitem_draft_flow_does_not_auto_execute(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed_pool(c); _set_patch(c, pool_id, item_id)
    c.post('/api/atlas/patch-proposals/planitem-draft', json={"pool_id": pool_id, "item_id": item_id, "run_id": "run_no_auto"}).json()
    events_path = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'pipeline_runs' / 'run_no_auto' / 'events.ndjson'
    events = events_path.read_text(encoding='utf-8') if events_path.exists() else ''
    for forbidden_event in ("safe_apply_manual_", "verification_", "debug_loop", "test_command"):
        assert forbidden_event not in events
    source = Path('agent/atlas_patch_proposal_planitem_service.py').read_text(encoding='utf-8')
    for token in ["safe_apply(", "execute_safe_apply", "runVerification", "TestCommandRunner(", "DebugLoopRunner(", "ImplementationExecutor", "subprocess", "shell=True", "run_command("]:
        assert token not in source
