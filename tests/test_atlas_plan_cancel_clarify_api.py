from pathlib import Path

from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_approval_service import POOL_CRITICAL_DECISION_ITEM_ID
from agent.atlas_critical_event_policy import normalize_critical_event
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path: Path, pool: AtlasPlanPool) -> TestClient:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    AtlasPlanPoolStorage(Path(tmp_path)).save_pool(pool)
    return TestClient(app)


def _pool(*, status="approval_required", item_status="approval_required", metadata=None) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_x",
        root_goal="Goal",
        status=status,
        items=[
            AtlasPlanItem(
                item_id="i1", pool_id="pool_x", title="Item", goal="Do",
                item_type="implementation", status=item_status, risk_level="medium",
                target_files=["src/i1.py"], metadata={"action_type": "create"},
            )
        ],
        metadata=metadata or {},
    )


def test_cancel_marks_pool_and_items_cancelled(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post("/api/atlas/plan-pools/pool_x/cancel", json={"reason": "user aborted"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_item_ids"] == ["i1"]
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.status == "cancelled"
    assert reloaded.get_item("i1").status == "cancelled"


def test_cancel_missing_pool_returns_404(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post("/api/atlas/plan-pools/nope/cancel", json={})
    assert r.status_code == 404


def test_approvals_decide_cancelled_marks_item_cancelled(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post("/api/atlas/approvals/decide", json={"pool_id": "pool_x", "item_id": "i1", "decision": "cancelled"})
    assert r.status_code == 200, r.text
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.get_item("i1").status == "cancelled"
    assert reloaded.get_item("i1").metadata["approval"]["decision"] == "cancelled"


def test_clarify_answers_one_question_and_preserves_pending_queue(tmp_path: Path):
    pool = _pool(metadata={
        "clarification_required": True,
        "clarification_questions": [
            {
                "question_id": "clar_q_1",
                "index": 1,
                "total": 2,
                "prompt": "Pick scope",
                "reason": "scope unclear",
                "options": [{"option_id": "minimal_scope", "label": "Minimal"}],
                "status": "pending",
            },
            {
                "question_id": "clar_q_2",
                "index": 2,
                "total": 2,
                "prompt": "Pick tests",
                "reason": "tests unclear",
                "options": [{"option_id": "smoke", "label": "Smoke"}],
                "status": "pending",
            },
        ],
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/plan-pools/pool_x/clarify",
        json={"question_id": "clar_q_1", "option_id": "minimal_scope", "answer_text": "one file"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["clarification_decision"]["question_id"] == "clar_q_1"
    assert body["pending_question_count"] == 1
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.metadata["clarification_required"] is True
    assert reloaded.metadata["clarification_questions"][0]["status"] == "answered"
    assert reloaded.metadata["clarification_questions"][1]["status"] == "pending"
    assert reloaded.metadata["plan_revision_required_after_clarification"] is True
    assert reloaded.metadata["gate_rerun_required_after_clarification"] is True


def test_clarify_clears_required_only_after_all_questions_answered(tmp_path: Path):
    pool = _pool(metadata={
        "clarification_required": True,
        "clarification_questions": [
            {
                "question_id": "clar_q_1",
                "index": 1,
                "total": 1,
                "prompt": "Pick scope",
                "reason": "scope unclear",
                "options": [{"option_id": "minimal_scope", "label": "Minimal"}],
                "status": "pending",
            },
        ],
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/plan-pools/pool_x/clarify",
        json={"question_id": "clar_q_1", "option_id": "minimal_scope", "answer_text": "one file"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending_question_count"] == 0
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert "clarification_required" not in (reloaded.metadata or {})
    assert reloaded.metadata["gate_rerun_required_after_clarification"] is False
    assert reloaded.metadata["gate_rerun_performed_after_clarification"] is True
    assert reloaded.metadata["plan_revision_required_after_clarification"] is False
    assert reloaded.metadata["revised_plan_snapshot"]
    assert "one file" in reloaded.root_goal
    assert reloaded.items[0].metadata["clarification_revision"]["answer_summary"]


def test_auto_safe_apply_blocks_until_clarification_replan_gate_rerun(tmp_path: Path):
    pool = _pool(status="ready", item_status="ready", metadata={
        "clarification_required": False,
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
        "plan_revision_required_after_clarification": True,
        "gate_rerun_required_after_clarification": True,
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/automation/safe-apply-one",
        json={"pool_id": "pool_x", "item_id": "i1", "preset_id": "guarded_low_risk"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "blocked"
    assert "plan_revision_required_after_clarification" in body["warnings"]
    assert "gate_rerun_required_after_clarification" in body["warnings"]


def test_ambiguous_plan_pool_pauses_at_needs_scope_confirmation(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Build a page with unclear scope not defined",
            "automation_features": {"clarification_mode": "pause"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "needs_scope_confirmation"
    metadata = body["plan_pool"]["metadata"]
    assert metadata["clarification_required"] is True
    assert metadata["clarification_questions"][0]["index"] == 1


def test_auto_clarification_records_safe_default_for_noncritical_ambiguity(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Build a page with unclear scope not defined",
            "automation_features": {"clarification_mode": "auto"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    metadata = body["plan_pool"]["metadata"]
    assert "safe_default_assumption_after_clarification" in metadata
    assert metadata.get("clarification_required") is not True


def test_critical_ambiguity_does_not_use_auto_default(tmp_path: Path):
    client = _client(tmp_path, _pool())
    r = client.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "Build unclear runtime command execution support",
            "automation_features": {"clarification_mode": "auto"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "needs_scope_confirmation"
    metadata = body["plan_pool"]["metadata"]
    assert metadata["clarification_required"] is True
    assert "safe_default_assumption_after_clarification" not in metadata


def test_answer_reducing_scope_updates_target_files_from_answer(tmp_path: Path):
    pool = _pool(metadata={
        "clarification_required": True,
        "clarification_questions": [
            {
                "question_id": "clar_q_1",
                "index": 1,
                "total": 1,
                "prompt": "Pick file",
                "reason": "scope unclear",
                "options": [{"option_id": "minimal_scope", "label": "Minimal"}],
                "status": "pending",
            },
        ],
    })
    pool.items[0].target_files = ["src/a.py", "src/b.py"]
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/plan-pools/pool_x/clarify",
        json={"question_id": "clar_q_1", "option_id": "minimal_scope", "answer_text": "Only src/a.py"},
    )
    assert r.status_code == 200, r.text
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.items[0].target_files == ["src/a.py"]
    assert reloaded.metadata["plan_revision_diff"]["scope_reduced"] is True


def test_answer_expanding_scope_triggers_critical_or_approval_status(tmp_path: Path):
    pool = _pool(metadata={
        "clarification_required": True,
        "clarification_questions": [
            {
                "question_id": "clar_q_1",
                "index": 1,
                "total": 1,
                "prompt": "Pick scope",
                "reason": "runtime scope unclear",
                "options": [{"option_id": "custom", "label": "Custom", "requires_text": True}],
                "status": "pending",
            },
        ],
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/plan-pools/pool_x/clarify",
        json={"question_id": "clar_q_1", "option_id": "custom", "answer_text": "Also add runtime command execution"},
    )
    assert r.status_code == 200, r.text
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.status in {"waiting_for_critical_decision", "approval_required"}
    assert reloaded.items[0].risk_level == "high"
    assert reloaded.metadata["plan_revision_diff"]["risk_raised"] is True


def test_pool_level_critical_decision_api_rejects_to_replanning(tmp_path: Path):
    event = normalize_critical_event(category="security", affected_files=["agent/security.py"])
    pool = AtlasPlanPool(
        pool_id="pool_x",
        root_goal="Change auth",
        status="waiting_for_critical_decision",
        items=[],
        metadata={"critical_event": event},
    )
    client = _client(tmp_path, pool)

    r = client.post(
        "/api/atlas/critical-decisions/decide",
        json={
            "pool_id": "pool_x",
            "item_id": POOL_CRITICAL_DECISION_ITEM_ID,
            "decision": "reject_ng_safer_replan",
            "reason": "Use safer path",
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["item_id"] == POOL_CRITICAL_DECISION_ITEM_ID
    assert body["approval_record"]["metadata"]["scope"] == "pool"
    assert body["approval_record"]["metadata"]["decision"] == "rejected_ng_safer_replan"
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.metadata["critical_replanning"]["original_path_blocked"] is True
    assert reloaded.items[0].metadata["created_from_critical_event"] is True
