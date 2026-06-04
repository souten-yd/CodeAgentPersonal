from pathlib import Path

from fastapi.testclient import TestClient

from app.server import create_app
from app.api import atlas_autonomous_codegen
from app.api import atlas_pipeline
from app.api.atlas_pipeline import _clarification_execution_block_reasons
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
    # The default _pool item is medium-risk, which the guarded_low_risk preset blocks at apply time;
    # the revised plan therefore surfaces as blocked_safety_review (a recoverable state with a
    # reason + override exit path) rather than a generic approval_required that silently re-blocks.
    assert body["clarification_replanning"]["status"] in {"ready", "approval_required", "waiting_for_critical_decision", "blocked_safety_review"}
    assert body["revised_plan_snapshot"]
    assert body["plan_revision_diff"]["root_goal_changed"] is True
    assert body["gate_rerun_summary"]
    assert body["revised_plan_summary"].startswith("Plan revised and gates rerun")
    assert body["next_required_user_action"]
    assert body["blocked_reasons"] == []
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert "clarification_required" not in (reloaded.metadata or {})
    assert reloaded.metadata["gate_rerun_required_after_clarification"] is False
    assert reloaded.metadata["gate_rerun_performed_after_clarification"] is True
    assert reloaded.metadata["plan_revision_required_after_clarification"] is False
    assert reloaded.metadata["revised_plan_snapshot"]
    assert reloaded.metadata["clarification_replanning"]["status"] == "completed"
    assert reloaded.metadata["revised_plan_summary"].startswith("Plan revised and gates rerun")
    assert reloaded.metadata["gate_rerun_summary"]
    assert "one file" in reloaded.root_goal
    assert reloaded.items[0].metadata["clarification_revision"]["answer_summary"]


def test_clarification_replanning_consumes_selected_option_impact(tmp_path: Path):
    pool = _pool(metadata={
        "clarification_required": True,
        "clarification_questions": [
            {
                "question_id": "clar_q_1",
                "index": 1,
                "total": 1,
                "title": "Game-over and restart behavior is missing",
                "prompt": "Choose how Atlas should revise the plan.",
                "reason": "Game plan lacks restart behavior.",
                "options": [
                    {
                        "option_id": "safest_recommended",
                        "label": "Recommended safe fix",
                        "description": "Add explicit game state transitions.",
                        "plan_change_summary": "Add playing -> game_over -> restart state and Space restart.",
                        "implementation_scope": "small_state_model",
                        "risk_level": "low",
                        "gate_rerun_required": True,
                        "can_continue_after_answer": False,
                    }
                ],
                "status": "pending",
            },
        ],
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/plan-pools/pool_x/clarify",
        json={"question_id": "clar_q_1", "option_id": "safest_recommended"},
    )
    assert r.status_code == 200, r.text

    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    answer = reloaded.metadata["clarification_answers"][0]
    assert answer["selected_option_impact"]["plan_change_summary"].startswith("Add playing")
    assert "playing -> game_over -> restart" in reloaded.root_goal
    item = reloaded.items[0]
    assert "playing -> game_over -> restart" in item.goal
    assert "small_state_model" in item.done_definition[-1]
    assert "rerun critique and safety gates after clarification" in item.test_commands
    assert item.metadata["verification_intent_after_clarification"]["gate_rerun_required"] is True
    assert item.metadata["clarification_revision"]["changed_fields"]
    impacts = reloaded.metadata["plan_revision_diff"]["selected_option_impacts"]
    assert impacts[0]["implementation_scope"] == "small_state_model"
    assert reloaded.metadata["changed_scope_summary"]
    assert reloaded.metadata["clarification_replanning"]["status"] == "completed"
    changed = reloaded.metadata["plan_revision_diff"]["item_changed_fields"]
    assert changed[0]["item_id"] == "i1"
    assert "goal" in changed[0]["changed_fields"]
    assert "test_commands" in changed[0]["changed_fields"]


def test_clarification_replanning_failure_keeps_execution_blocked(tmp_path: Path, monkeypatch):
    pool = _pool(status="ready", item_status="ready", metadata={
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

    def fail_gate(*_args, **_kwargs):
        raise RuntimeError("synthetic gate rerun failure with internal detail")

    monkeypatch.setattr(atlas_pipeline.AtlasClarificationReplanningService, "_rerun_safety_gate", fail_gate)
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/plan-pools/pool_x/clarify",
        json={"question_id": "clar_q_1", "option_id": "minimal_scope", "answer_text": "one file"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["clarification_replanning"]["status"] == "failed"
    assert "RuntimeError: synthetic gate rerun failure" in body["clarification_replanning"]["error_summary"]
    assert "Traceback" not in body["clarification_replanning"]["error_summary"]
    assert "plan_revision_required_after_clarification" in body["blocked_reasons"]
    assert "gate_rerun_required_after_clarification" in body["blocked_reasons"]
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    assert reloaded.status != "ready"
    assert reloaded.metadata["clarification_replanning"]["status"] == "failed"
    assert reloaded.metadata["plan_revision_required_after_clarification"] is True
    assert reloaded.metadata["gate_rerun_required_after_clarification"] is True
    assert reloaded.metadata["gate_rerun_performed_after_clarification"] is False


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
    assert "missing_revised_plan_snapshot_after_clarification" in body["warnings"]
    assert "missing_gate_rerun_evidence_after_clarification" in body["warnings"]
    assert body["metadata"]["clarification_execution_blocked"] is True


def test_safe_apply_and_verify_blocks_until_clarification_replan_gate_rerun(tmp_path: Path):
    pool = _pool(status="ready", item_status="ready", metadata={
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
        "revised_plan_snapshot": {"root_goal": "Revised"},
        "gate_rerun_required_after_clarification": True,
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/automation/safe-apply-one-and-verify",
        json={"pool_id": "pool_x", "item_id": "i1", "preset_id": "guarded_low_risk", "command_id": "pytest"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "safe_apply_blocked"
    safe = body["auto_safe_apply_result"]
    assert safe["status"] == "blocked"
    assert safe["metadata"]["clarification_execution_blocked"] is True
    assert safe["metadata"]["blocked_reasons"] == [
        "gate_rerun_required_after_clarification",
        "missing_gate_rerun_evidence_after_clarification",
    ]
    verify = body["auto_verification_result"]
    assert verify["status"] == "skipped"
    assert verify["warnings"] == ["safe_apply_not_applied"]


def test_patch_proposal_generation_blocks_before_service_for_clarification_required(tmp_path: Path, monkeypatch):
    pool = _pool(status="ready", item_status="ready", metadata={"clarification_required": True})
    client = _client(tmp_path, pool)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("proposal service must not run while clarification is blocked")

    monkeypatch.setattr(atlas_pipeline.AtlasPatchProposalService, "propose_for_item", fail_if_called)
    r = client.post(
        "/api/atlas/patch-proposals/generate",
        json={"pool_id": "pool_x", "item_id": "i1", "source_type": "plan_item"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "blocked"
    assert body["metadata"]["clarification_execution_blocked"] is True
    assert body["metadata"]["blocked_reasons"] == ["clarification_required"]
    assert body["plan_pool"]["pool_id"] == "pool_x"


def test_patch_proposal_generation_blocks_missing_revised_plan_snapshot(tmp_path: Path):
    pool = _pool(status="ready", item_status="ready", metadata={
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
        "rerun_critique_gate_after_clarification": {"status": "passed"},
        "rerun_safety_gate_after_clarification": {"status": "passed"},
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/patch-proposals/generate",
        json={"pool_id": "pool_x", "item_id": "i1", "source_type": "plan_item"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "blocked"
    assert body["warnings"] == ["missing_revised_plan_snapshot_after_clarification"]


def test_patch_proposal_generation_blocks_missing_gate_rerun_evidence(tmp_path: Path):
    pool = _pool(status="ready", item_status="ready", metadata={
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
        "revised_plan_snapshot": {"root_goal": "Revised"},
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/patch-proposals/generate",
        json={"pool_id": "pool_x", "item_id": "i1", "source_type": "plan_item"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "blocked"
    assert body["warnings"] == ["missing_gate_rerun_evidence_after_clarification"]


def test_patch_proposal_decide_blocks_approval_during_clarification(tmp_path: Path):
    pool = _pool(status="ready", item_status="ready", metadata={"clarification_required": True})
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/patch-proposals/decide",
        json={"pool_id": "pool_x", "item_id": "i1", "proposal_id": "p1", "decision": "approved"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "blocked"
    assert body["metadata"]["clarification_execution_blocked"] is True


def test_autonomous_codegen_start_blocks_before_orchestrator_for_clarification(tmp_path: Path, monkeypatch):
    pool = _pool(status="ready", item_status="ready", metadata={
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
        "plan_revision_required_after_clarification": True,
    })
    client = _client(tmp_path, pool)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("orchestrator must not run while clarification is blocked")

    monkeypatch.setattr(atlas_autonomous_codegen, "_orchestrator_service", fail_if_called)
    r = client.post("/api/atlas/autonomous-codegen/start", json={"pool_id": "pool_x"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "blocked_safety_review"
    assert body["phase"] == "revising_plan_from_clarification"
    assert body["stop_reason"] == "clarification_revision_gate_rerun_required"
    assert body["metadata"]["clarification_execution_blocked"] is True


def test_clarification_execution_block_reasons_cover_required_tokens():
    pool = _pool(metadata={
        "clarification_required": True,
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
        "plan_revision_required_after_clarification": True,
        "gate_rerun_required_after_clarification": True,
    })
    reasons = _clarification_execution_block_reasons(pool)
    assert reasons == [
        "clarification_required",
        "plan_revision_required_after_clarification",
        "gate_rerun_required_after_clarification",
        "missing_revised_plan_snapshot_after_clarification",
        "missing_gate_rerun_evidence_after_clarification",
    ]


def test_clarification_execution_block_allows_historical_answers_with_evidence():
    pool = _pool(metadata={
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
        "revised_plan_snapshot": {"root_goal": "Revised"},
        "rerun_critique_gate_after_clarification": {"status": "passed"},
        "rerun_safety_gate_after_clarification": {"status": "passed"},
        "plan_revision_required_after_clarification": False,
        "gate_rerun_required_after_clarification": False,
    })
    assert _clarification_execution_block_reasons(pool) == []


def test_manual_safe_apply_blocks_before_service_for_clarification(tmp_path: Path):
    pool = _pool(status="ready", item_status="ready", metadata={
        "clarification_required": True,
        "clarification_answers": [{"question_id": "clar_q_1", "option_id": "minimal_scope"}],
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/safe-apply/execute",
        json={"pool_id": "pool_x", "item_id": "i1", "run_id": "run_1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "blocked"
    assert body["metadata"]["clarification_execution_blocked"] is True
    assert "clarification_required" in body["warnings"]


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
    assert metadata["safe_default_clarification_mode"] == "auto"
    assert metadata.get("clarification_required") is not True
    assert metadata["pending_question_count"] == 0
    assert metadata["answered_question_count"] >= 1
    assert metadata["clarification_answers"][0]["option_id"] == "safest_recommended"
    assert metadata["revised_plan_snapshot"]
    assert metadata["gate_rerun_performed_after_clarification"] is True
    assert metadata["plan_revision_required_after_clarification"] is False
    assert metadata["gate_rerun_required_after_clarification"] is False
    assert metadata["allowed_paths_after_clarification"] == []
    assert metadata["blocked_paths_after_clarification"] == []
    assert _clarification_execution_block_reasons(AtlasPlanPool.model_validate(body["plan_pool"])) == []


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
    assert reloaded.metadata["allowed_paths_after_clarification"] == ["src/a.py"]
    assert reloaded.metadata["blocked_paths_after_clarification"] == []
    assert reloaded.metadata["plan_revision_diff"]["allowed_paths_after_clarification"] == ["src/a.py"]
    assert reloaded.items[0].metadata["allowed_paths_after_clarification"] == ["src/a.py"]
    changed = reloaded.metadata["plan_revision_diff"]["item_changed_fields"]
    assert changed == [{"item_id": "i1", "changed_fields": ["description", "done_definition", "expected_changes", "goal", "target_files"]}]
    assert reloaded.metadata["plan_revision_diff"]["scope_reduced"] is True


def test_answer_changing_tests_persists_structured_verification_intent(tmp_path: Path):
    pool = _pool(metadata={
        "clarification_required": True,
        "clarification_questions": [
            {
                "question_id": "clar_q_1",
                "index": 1,
                "total": 1,
                "prompt": "Pick verification",
                "reason": "test scope unclear",
                "options": [{"option_id": "smoke", "label": "Smoke test"}],
                "status": "pending",
            },
        ],
    })
    client = _client(tmp_path, pool)
    r = client.post(
        "/api/atlas/plan-pools/pool_x/clarify",
        json={"question_id": "clar_q_1", "option_id": "smoke", "answer_text": "Run smoke test for the changed UI"},
    )
    assert r.status_code == 200, r.text

    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    intent = reloaded.items[0].metadata["verification_intent_after_clarification"]
    assert intent["selected_verification"] == "Smoke test: Run smoke test for the changed UI"
    assert intent["gate_rerun_required"] is True
    assert intent["can_continue_after_answer"] is False
    assert "focused verification selected by clarification" in reloaded.items[0].test_commands
    changed = reloaded.metadata["plan_revision_diff"]["item_changed_fields"][0]["changed_fields"]
    assert "test_commands" in changed


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


def test_pool_level_critical_approval_persists_bounded_scope(tmp_path: Path):
    event = normalize_critical_event(category="security", affected_files=["agent/security.py"])
    pool = AtlasPlanPool(
        pool_id="pool_x",
        root_goal="Change auth",
        status="waiting_for_critical_decision",
        items=[
            AtlasPlanItem(
                item_id="i1",
                pool_id="pool_x",
                title="Security item",
                goal="Change auth safely",
                item_type="implementation",
                status="waiting_for_critical_decision",
                risk_level="critical",
                target_files=["agent/security.py"],
                metadata={"critical_event": event},
            )
        ],
        metadata={"critical_event": event},
    )
    client = _client(tmp_path, pool)

    r = client.post(
        "/api/atlas/critical-decisions/decide",
        json={
            "pool_id": "pool_x",
            "item_id": POOL_CRITICAL_DECISION_ITEM_ID,
            "decision": "approved",
            "reason": "Allow only the reviewed file",
            "metadata": {
                "approved_files": ["agent/security.py"],
                "approved_item_ids": ["i1"],
                "approved_capabilities": ["security"],
            },
        },
    )

    assert r.status_code == 200, r.text
    reloaded = AtlasPlanPoolStorage(Path(tmp_path)).load_pool("pool_x")
    decision = reloaded.metadata["critical_decision"]
    assert decision["decision"] == "approved"
    assert decision["approved_files"] == ["agent/security.py"]
    assert decision["approved_scope"] == ["agent/security.py"]
    assert decision["approved_paths"] == ["agent/security.py"]
    assert decision["approved_item_ids"] == ["i1"]
    assert decision["approved_capabilities"] == ["security"]
    assert decision["bounded_continuation"] is True
    approval_metadata = r.json()["approval_record"]["metadata"]
    assert approval_metadata["approved_files"] == ["agent/security.py"]
    assert approval_metadata["approved_item_ids"] == ["i1"]
