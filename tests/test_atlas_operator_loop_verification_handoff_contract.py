from fastapi.testclient import TestClient

from app.server import create_app


def _create_pool(client: TestClient, *, metadata=None, item_metadata=None):
    payload = {
        "workspace_id": "default",
        "input": "Implement one thing",
        "mode": "local",
        "project_path": ".",
        "enable_repo_context": False,
        "metadata": metadata or {},
        "plan": {
            "goal": "g",
            "tasks": [{"id": "item_1", "title": "Task", "description": "Do", "status": "pending", "metadata": item_metadata or {}}],
        },
    }
    r = client.post('/api/atlas/plan-pools', json=payload)
    assert r.status_code == 200
    return r.json()["pool_id"]


def _prepare(client: TestClient, pool_id: str):
    b = client.post('/api/atlas/multi-item-supervised-status/build', json={"pool_id": pool_id, "dry_run": True})
    assert b.status_code == 200
    msid = b.json()["multi_status_run_id"]
    p = client.post('/api/atlas/next-action-orchestrator/prepare', json={"pool_id": pool_id, "multi_status_run_id": msid, "build_queue_if_missing": False})
    assert p.status_code == 200
    return p.json()


def test_prepare_includes_pool_level_handoff_and_safety_flags(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path); c = TestClient(app)
    pid = _create_pool(c, metadata={"verification_recommendation_handoff": {"approval_summary": "pool", "confidence": "medium"}})
    out = _prepare(c, pid)
    handoff = out["action_contract"]["metadata"].get("verification_recommendation_handoff")
    assert handoff and handoff["approval_summary"] == "pool"
    for k, v in {"advisory_only": True, "executed": False, "manual_approval_only": True, "commands_are_suggestions_only": True, "auto_verification_triggered": False, "auto_test_execution_triggered": False}.items():
        assert handoff[k] is v


def test_item_level_handoff_overrides_pool_level(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path); c = TestClient(app)
    pid = _create_pool(
        c,
        metadata={"verification_recommendation_handoff": {"approval_summary": "pool"}},
        item_metadata={"verification_recommendation_handoff": {"approval_summary": "item", "warnings": ["w1"]}},
    )
    out = _prepare(c, pid)
    handoff = out["action_contract"]["metadata"]["verification_recommendation_handoff"]
    assert handoff["approval_summary"] in {"item","pool"}


def test_missing_handoff_non_blocking_and_confirmation_semantics_unchanged(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path); c = TestClient(app)
    pid = _create_pool(c)
    out = _prepare(c, pid)
    assert out["status"] in {"action_ready", "manual_display", "blocked", "no_action", "dry_run"}
    md = out["action_contract"]["metadata"]
    assert "verification_recommendation_handoff_unavailable" in md.get("verification_recommendation_handoff", {}).get("warnings", [])

    svc_text = __import__("pathlib").Path("agent/atlas_guarded_operator_loop_service.py").read_text(encoding="utf-8")
    assert "EXECUTE ONE ACTION" in svc_text
    assert "require_dry_run_first" in svc_text


def test_item_override_priority_via_pool_artifact_mutation(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path); c = TestClient(app)
    pid = _create_pool(c, metadata={"verification_recommendation_handoff": {"approval_summary": "pool"}})
    import json
    pool_file = next((tmp_path / "atlas" / "plan_pools").glob(f"{pid}.json"))
    data = json.loads(pool_file.read_text(encoding="utf-8"))
    data["items"][0].setdefault("metadata", {})["verification_recommendation_handoff"] = {"approval_summary": "item"}
    pool_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    out = _prepare(c, pid)
    assert out["action_contract"]["metadata"]["verification_recommendation_handoff"]["approval_summary"] == "item"
