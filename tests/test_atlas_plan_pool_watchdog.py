from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import main
from app.api.atlas_pipeline import _merge_plan_pool_job, _write_plan_pool_job


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    main.app.state.atlas_memory_search_fn = None
    main.app.state.atlas_active_skills_fn = None
    return TestClient(main.app)


def _iso(seconds_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def test_merge_plan_pool_job_preserves_status_and_adds_progress(tmp_path) -> None:
    _write_plan_pool_job(tmp_path, "pool_watch", {"pool_id": "pool_watch", "status": "running"})

    _merge_plan_pool_job(tmp_path, "pool_watch", {"phase": "plan_generation", "last_progress_at": _iso()})

    client = _client(tmp_path)
    response = client.get("/api/atlas/plan-pools/pool_watch/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["current_phase"] == "plan_generation"
    assert body["is_stalled"] is False


def test_status_marks_running_job_stalled_after_progress_threshold(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_PLAN_STALL_AFTER_SEC", "1")
    _write_plan_pool_job(tmp_path, "pool_stalled", {
        "pool_id": "pool_stalled",
        "status": "running",
        "created_at": _iso(10),
        "last_progress_at": _iso(10),
        "phase": "adversarial_critique",
    })

    response = _client(tmp_path).get("/api/atlas/plan-pools/pool_stalled/status")

    assert response.status_code == 200
    body = response.json()
    assert body["is_stalled"] is True
    assert body["current_phase"] == "adversarial_critique"
    assert body["seconds_since_progress"] >= 1
    assert "stalled_reason" in body
    assert "suggested_action" in body


def test_status_does_not_stall_fresh_terminal_or_queued_jobs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_PLAN_STALL_AFTER_SEC", "1")
    for status in ("running", "ready", "failed", "queued"):
        _write_plan_pool_job(tmp_path, f"pool_{status}", {
            "pool_id": f"pool_{status}",
            "status": status,
            "created_at": _iso(10),
            "last_progress_at": _iso(0 if status == "running" else 10),
            "phase": status,
        })
        response = _client(tmp_path).get(f"/api/atlas/plan-pools/pool_{status}/status")
        assert response.status_code == 200
        assert response.json()["is_stalled"] is False


def test_status_uses_recent_token_heartbeat_over_old_phase_progress(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_PLAN_STALL_AFTER_SEC", "1")
    _write_plan_pool_job(tmp_path, "pool_tokens", {
        "pool_id": "pool_tokens",
        "status": "running",
        "created_at": _iso(10),
        "last_progress_at": _iso(10),
        "last_token_at": _iso(0),
        "tokens_generated": 42,
        "phase": "plan_generation",
    })

    response = _client(tmp_path).get("/api/atlas/plan-pools/pool_tokens/status")

    assert response.status_code == 200
    body = response.json()
    assert body["is_stalled"] is False
    assert body["tokens_generated"] == 42
