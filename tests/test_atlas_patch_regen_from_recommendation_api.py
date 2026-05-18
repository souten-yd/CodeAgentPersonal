import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_patch_regen_from_recommendation import router
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def setup_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage = AtlasPlanPoolStorage("ca_data")
    item = AtlasPlanItem(pool_id="p1", item_id="i1", title="t", goal="g", metadata={"patch":"diff --git a/src/a.py b/src/a.py", "target_files":["src/a.py"], "verification":{"error":"AssertionError"}})
    storage.save_pool(AtlasPlanPool(pool_id="p1", root_goal="g", items=[item]))
    rec = {"pool_id":"p1","item_id":"i1","run_id":"run1","handoff_id":"handoff_abc123","safe_apply_execution_id":"safehandoff_abc123","verification_run_id":"verifyhandoff_abc123","supervised_retry_run_id":"retryhandoff_abc123","recommendation_run_id":"regenrec_abc123","policy_id":"patch_regen_recommendation_v1","patch_regen_policy_id":"supervised_patch_regen_v1","status":"recommendation_ready","recommended_payload":{"pool_id":"p1","item_id":"i1","verification_result":{"error":"AssertionError test failed"},"bounded_retry_result":{"status":"exhausted"},"failure_stop_suggestion":{"stop":True},"original_patch":"diff --git a/src/a.py b/src/a.py","changed_files":["src/a.py"],"target_files":["src/a.py"],"metadata":{}},"warnings":[],"errors":[],"metadata":{"auto_execute_patch_regen":False,"side_effects":{"patch_regeneration_executed":False,"safe_apply_executed":False,"verification_executed":False}}}
    root = Path("ca_data/atlas/patch_regen_recommendations/p1"); root.mkdir(parents=True, exist_ok=True)
    root.joinpath("regenrec_abc123.json").write_text(json.dumps(rec), encoding="utf-8")


def client():
    app = FastAPI(); app.include_router(router); return TestClient(app)


def test_api_run_patch_regen_from_recommendation(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    c = client()
    payload = {"pool_id":"p1","item_id":"i1","recommendation_run_id":"regenrec_abc123","reviewer":"manual","reason":"api"}
    run = c.post("/api/atlas/patch-regen-from-recommendation/run", json=payload)
    assert run.status_code == 200
    body = run.json()
    assert body["status"] in {"patch_regen_created", "blocked"}
    assert body["recommendation_exec_id"].startswith("regenexec_")
    got = c.get(f"/api/atlas/patch-regen-from-recommendation/results/p1/{body['recommendation_exec_id']}")
    assert got.status_code == 200
    latest = c.post("/api/atlas/patch-regen-from-recommendation/latest", json={"pool_id":"p1"})
    assert latest.status_code == 200
    assert latest.json()["recommendation_exec_id"] == body["recommendation_exec_id"]


def test_api_path_traversal_rejected(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    c = client()
    assert c.post("/api/atlas/patch-regen-from-recommendation/run", json={"pool_id":"../x","item_id":"i1","recommendation_run_id":"regenrec_abc123"}).status_code == 400
    assert c.post("/api/atlas/patch-regen-from-recommendation/run", json={"pool_id":"p1","item_id":"../x","recommendation_run_id":"regenrec_abc123"}).status_code == 400
    assert c.post("/api/atlas/patch-regen-from-recommendation/run", json={"pool_id":"p1","item_id":"i1","recommendation_run_id":"bad"}).status_code == 400
    assert c.get("/api/atlas/patch-regen-from-recommendation/results/p1/bad").status_code == 400


def test_no_task_agent_routes():
    paths = [route.path for route in client().app.routes]
    assert not any(path.startswith("/api/task/") or path.startswith("/api/agent/") for path in paths)
