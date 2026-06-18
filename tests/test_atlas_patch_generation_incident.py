from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import AtlasAutopilotItemResult, AtlasMultiItemAutopilotResult
from agent.atlas_patch_generation_state import is_patch_generation_success, reduce_patch_generation_state
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest
from agent.atlas_self_correction_service import AtlasSelfCorrectionService


def _client(tmp_path: Path, llm=None) -> TestClient:
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = llm
    return TestClient(main.app)


def _item() -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Create HTML",
        goal="Display HelloWorld",
        description="Create hello_world.html displaying HelloWorld.",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["hello_world.html"],
        requirement_ids=["req_001"],
        acceptance_criteria=["HelloWorld appears"],
        verification_contract={"contract_id": "static_html", "signals": ["HelloWorld"]},
        metadata={"action_type": "create"},
    )


def _pool(tmp_path: Path, item: AtlasPlanItem | None = None) -> AtlasPlanPool:
    item = item or _item()
    return AtlasPlanPool(
        pool_id=item.pool_id,
        root_goal="Create HelloWorld HTML",
        original_user_request="Create a simple HTML file displaying HelloWorld.",
        requirements=[{"requirement_id": "req_001", "description": "Display HelloWorld", "required": True}],
        requirement_item_map={"req_001": [item.item_id]},
        project_path=str(tmp_path),
        status="ready",
        items=[item],
    )


def _store(tmp_path: Path, pool: AtlasPlanPool) -> tuple[AtlasPlanPoolStorage, AtlasJournal]:
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return storage, journal


def _llm_success(_system: str, _user: str) -> dict:
    return {
        "target_files": ["hello_world.html"],
        "proposed_content": "<!doctype html><html><body>HelloWorld</body></html>",
        "satisfied_requirement_ids": ["req_001"],
        "implemented_symbols": ["hello_world.html"],
        "behavioral_cases": ["Display HelloWorld"],
        "verification_cases": ["static html"],
    }


def test_duplicate_active_generation_returns_existing_run_and_same_run_is_idempotent(tmp_path: Path) -> None:
    item = _item()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    item.metadata["patch_generation"] = {
        "run_id": "run_active",
        "state": "repairing",
        "outcome": "active",
        "attempt": 2,
        "strategy": "deterministic_contract_or_metadata_repair",
        "updated_at": stale,
    }
    pool = _pool(tmp_path, item)
    storage, journal = _store(tmp_path, pool)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_success)

    duplicate = service.propose_for_item(AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", run_id="run_other", source_type="plan_item"))
    same = service.propose_for_item(AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", run_id="run_active", source_type="plan_item"))

    assert duplicate.status == "blocked"
    assert duplicate.metadata["active_run_id"] == "run_active"
    assert "patch_generation_active_run_exists" in duplicate.warnings
    assert same.metadata["idempotent"] is True
    assert same.metadata["patch_generation"]["state"] == "repairing"


def test_stale_active_run_is_recovered_before_new_generation(tmp_path: Path) -> None:
    item = _item()
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    item.metadata["patch_generation"] = {"run_id": "run_stale", "state": "running", "outcome": "active", "updated_at": stale}
    pool = _pool(tmp_path, item)
    storage, journal = _store(tmp_path, pool)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_success)

    result = service.propose_for_item(AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", run_id="run_new", source_type="plan_item"))

    assert result.metadata["patch_generation"]["run_id"] == "run_new"
    assert result.metadata["patch_generation"]["outcome"] == "success"
    events = "\n".join(p.read_text(encoding="utf-8") for p in Path(tmp_path).rglob("events.ndjson"))
    assert "stale_active_patch_generation_run" in events


def test_cancel_requires_matching_active_run_id(tmp_path: Path) -> None:
    item = _item()
    item.metadata["patch_generation"] = {"run_id": "run_active", "state": "repairing", "outcome": "active", "updated_at": datetime.now(timezone.utc).isoformat()}
    _store(tmp_path, _pool(tmp_path, item))
    client = _client(tmp_path)

    wrong = client.post("/api/atlas/patch-proposals/cancel", json={"pool_id": "pool_1", "item_id": "item_1", "run_id": "wrong"}).json()
    right = client.post("/api/atlas/patch-proposals/cancel", json={"pool_id": "pool_1", "item_id": "item_1", "run_id": "run_active"}).json()

    assert wrong["status"] == "blocked"
    assert "patch_generation_run_id_mismatch" in wrong["warnings"]
    assert right["status"] == "cancelled"
    assert right["patch_generation"]["state"] == "cancelled"


def test_runtime_reconciliation_prefers_newer_success_over_older_failed_state(tmp_path: Path) -> None:
    item = _item()
    item.metadata["patch_generation"] = {
        "run_id": "run_old",
        "state": "failed",
        "outcome": "failure",
        "reason_code": "old_failure",
        "updated_at": "2026-06-07T00:00:00+00:00",
    }
    item.metadata["patch_proposal"] = {
        "status": "proposed",
        "proposal_id": "p1",
        "metadata": {
            "patch_content_available": True,
            "patch_generation": {
                "run_id": "run_new",
                "state": "succeeded",
                "outcome": "success",
                "patch_content_available": True,
                "updated_at": "2026-06-07T01:00:00+00:00",
            },
        },
    }
    _storage, journal = _store(tmp_path, _pool(tmp_path, item))
    journal.append_event("pool_1", "run_old", {
        "event_type": "patch_generation_failed",
        "pool_id": "pool_1",
        "run_id": "run_old",
        "item_id": "item_1",
        "state": "failed",
        "outcome": "failure",
        "reason_code": "old_failure",
        "patch_generation": item.metadata["patch_generation"],
        "created_at": "2026-06-07T00:00:00+00:00",
    })
    body = _client(tmp_path).get("/api/atlas/plan-pools/pool_1/runtime-status").json()

    assert body["patch_generation"]["run_id"] == "run_new"
    assert body["status"] == "completed"
    assert any(d["type"] == "proposal_patch_generation_newer_than_item_metadata" for d in body["reconciliation_diagnostics"])
    assert any(d["type"] == "terminal_lifecycle_event_authoritative" for d in body["reconciliation_diagnostics"])


def test_non_success_patch_generation_cannot_enable_approval_apply_verify_or_completed_ui() -> None:
    files = {
        "approval": Path("agent/atlas_patch_proposal_approval_service.py").read_text(encoding="utf-8"),
        "draft": Path("agent/atlas_patch_proposal_planitem_service.py").read_text(encoding="utf-8"),
        "apply": Path("agent/atlas_file_safe_apply_executor.py").read_text(encoding="utf-8"),
        "orchestrator": Path("agent/atlas_autonomous_codegen_orchestrator_service.py").read_text(encoding="utf-8"),
        "self_correction": Path("agent/atlas_self_correction_service.py").read_text(encoding="utf-8"),
        "dashboard": Path("web/js/atlas_dashboard.js").read_text(encoding="utf-8"),
        "claude_panel": Path("web/js/atlas_claude_panel.js").read_text(encoding="utf-8"),
    }
    for key in ("approval", "draft", "apply", "orchestrator", "self_correction"):
        assert "is_patch_generation_success" in files[key]
    assert "patchGeneration.state === 'succeeded'" in files["dashboard"]
    assert "patchGeneration.outcome === 'success'" in files["dashboard"]
    assert "patchGeneration.state === 'succeeded'" in files["claude_panel"]
    assert "patchGeneration.outcome === 'success'" in files["claude_panel"]


def test_reducer_is_pure_and_records_repair_attempt_strategy() -> None:
    current = {"run_id": "r1", "state": "running", "outcome": "active", "history": []}
    event = {
        "event_type": "patch_validation_failed",
        "run_id": "r1",
        "attempt": 2,
        "strategy": "deterministic_contract_or_metadata_repair",
        "reason_code": "semantic_validation_failed",
    }
    next_state = reduce_patch_generation_state(current, event)

    assert current["state"] == "running"
    assert next_state["state"] == "repairing"
    assert next_state["attempt"] == 2
    assert next_state["strategy"] == "deterministic_contract_or_metadata_repair"


# ── semantic_evidence_missing incident: deterministic evidence backfill ──────────────────────


def _llm_content_only(_system: str, _user: str) -> dict:
    """Mirrors the real weak local model: valid file content but NO advisory evidence fields
    (implemented_symbols / behavioral_cases / verification_cases). This is exactly the payload that
    previously failed with semantic_validation_failed:semantic_evidence_missing."""
    return {
        "target_files": ["hello_world.html"],
        "proposed_content": "<!doctype html><html><body>HelloWorld</body></html>",
        "satisfied_requirement_ids": ["req_001"],
        "risk_level": "low",
    }


def _llm_empty_content(_system: str, _user: str) -> dict:
    return {"target_files": ["hello_world.html"], "proposed_content": ""}


class _FakeAutopilot:
    """Stands in for apply+verify so the orchestrator E2E exercises generation -> apply -> summary."""

    def __init__(self, status: str = "completed") -> None:
        self.status = status
        self.requests: list = []

    def run(self, request):
        self.requests.append(request)
        item_id = request.item_ids[0] if request.item_ids else "item_1"
        completed = self.status in {"completed", "partial"}
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id,
            run_id=request.run_id,
            autopilot_run_id="auto_test",
            policy_id=request.policy_id,
            status=self.status,
            processed_count=1,
            completed_count=1 if completed else 0,
            item_results=[
                AtlasAutopilotItemResult(
                    item_id=item_id,
                    status=self.status,
                    changed_files=["hello_world.html"] if completed else [],
                    verification_result={"status": "passed"} if completed else {"status": "failed"},
                )
            ],
            created_at="2026-06-01T00:00:00+00:00",
        )


def test_evidence_omitted_content_still_succeeds_via_inference(tmp_path: Path) -> None:
    """A weak model that returns content but omits evidence fields must NOT fail with
    semantic_evidence_missing — the service infers evidence deterministically from content + plan."""
    pool = _pool(tmp_path)
    storage, journal = _store(tmp_path, pool)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_content_only)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", run_id="run_1", source_type="plan_item")
    )

    assert result.status == "proposed"
    assert is_patch_generation_success((result.metadata or {}).get("patch_generation")) is True
    proposal_md = result.proposal.metadata
    assert proposal_md.get("semantic_evidence_inferred")  # records which evidence keys were backfilled
    assert proposal_md.get("implemented_symbols")
    semantic = proposal_md.get("semantic_validation") or {}
    assert "semantic_evidence_missing" not in (semantic.get("reasons") or [])
    assert semantic.get("status") == "passed"
    reloaded = storage.load_pool("pool_1")
    assert reloaded.get_item("item_1").status == "ready"
    assert reloaded.status == "ready"
    assert reloaded.metadata["patch_generation_pool_summary"]["terminal"] is False


def test_empty_generated_content_still_fails_honestly(tmp_path: Path) -> None:
    """Evidence backfill only runs when real content exists; an empty generation must still fail
    (no fabricated success)."""
    pool = _pool(tmp_path)
    storage, journal = _store(tmp_path, pool)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_empty_content)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", run_id="run_1", source_type="plan_item")
    )

    assert result.status != "proposed"
    assert is_patch_generation_success((result.metadata or {}).get("patch_generation")) is False
    assert (result.proposal.metadata or {}).get("patch_content_available") is False
    reloaded = storage.load_pool("pool_1")
    assert reloaded.get_item("item_1").status == "failed"
    assert reloaded.status == "failed"
    assert reloaded.current_item_id == ""
    assert reloaded.metadata["patch_generation_pool_summary"]["terminal"] is True


def test_patch_generation_failure_returns_pool_to_ready_when_other_items_remain(tmp_path: Path) -> None:
    first = _item()
    second = _item().model_copy(
        update={
            "item_id": "item_2",
            "title": "Create CSS",
            "goal": "Create styles",
            "target_files": ["style.css"],
            "requirement_ids": ["req_002"],
        }
    )
    pool = _pool(tmp_path, first)
    pool.items.append(second)
    pool.requirements.append({"requirement_id": "req_002", "description": "Create styles", "required": True})
    pool.requirement_item_map["req_002"] = ["item_2"]
    storage, journal = _store(tmp_path, pool)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_empty_content)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_1", run_id="run_1", source_type="plan_item")
    )

    assert result.status == "failed"
    reloaded = storage.load_pool("pool_1")
    assert reloaded.get_item("item_1").status == "failed"
    assert reloaded.get_item("item_2").status == "ready"
    assert reloaded.status == "ready"
    assert reloaded.metadata["patch_generation_pool_summary"]["terminal"] is False


def test_route1_plan_approve_patch_verify_summary_completes(tmp_path: Path) -> None:
    """Route ①: plan -> approve -> patch -> approve -> verify -> summary completes end to end even
    when the model omits evidence fields (the incident scenario)."""
    pool = _pool(tmp_path)
    storage, journal = _store(tmp_path, pool)
    proposal_service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_content_only)
    autopilot = _FakeAutopilot("completed")
    orchestrator = AtlasAutonomousCodegenOrchestratorService(
        storage=storage,
        journal=journal,
        patch_proposal_service=proposal_service,
        multi_item_autopilot_service=autopilot,
    )

    out = orchestrator.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "completed"
    assert out.phase == "final_summary"
    assert out.generated_count == 1
    assert autopilot.requests  # apply/verify phase ran


def test_route2_revision_required_blocks_then_completes_after_revision(tmp_path: Path) -> None:
    """Route ②: plan -> revise -> approve -> patch -> approve -> verify -> summary. The
    plan_revision_required flag blocks patch generation; clearing it (revise+approve) lets the same
    path complete."""
    pool = _pool(tmp_path)
    pool.metadata = {**(pool.metadata or {}), "plan_revision_required": True}
    storage, journal = _store(tmp_path, pool)
    proposal_service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_content_only)
    autopilot = _FakeAutopilot("completed")
    orchestrator = AtlasAutonomousCodegenOrchestratorService(
        storage=storage,
        journal=journal,
        patch_proposal_service=proposal_service,
        multi_item_autopilot_service=autopilot,
    )

    blocked = orchestrator.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))
    assert blocked.status == "blocked_safety_review"
    assert blocked.stop_reason == "plan_revision_required"
    assert autopilot.requests == []  # never reached patch generation / apply

    # Revise + approve: clear the gate flag.
    revised = storage.load_pool("pool_1")
    revised.metadata = {k: v for k, v in (revised.metadata or {}).items() if k != "plan_revision_required"}
    storage.save_pool(revised)

    out = orchestrator.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))
    assert out.status == "completed"
    assert out.generated_count == 1
    assert autopilot.requests  # apply/verify ran after revision


class _FakeApply:
    def __init__(self, status: str = "applied") -> None:
        self.status = status
        self.changed_files = ["hello_world.html"]

    def execute_one(self, request):
        outer = self

        class _R:
            status = outer.status
            changed_files = outer.changed_files

        return _R()


class _FakeVerify:
    """Fails the first N re-verifications, then passes (drives the self-correction loop)."""

    def __init__(self, fail_times: int = 1) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def run_after_auto_safe_apply(self, request):
        self.calls += 1
        status = "failed" if self.calls <= self.fail_times else "passed"

        class _R:
            def __init__(self, status: str) -> None:
                self.status = status
                self.warnings: list = []

            def model_dump(self):
                return {"status": self.status, "stdout_tail": "", "stderr_tail": "boom", "exit_code": 1}

        return _R(status)


def test_route3_ng_self_correction_loop_recovers(tmp_path: Path) -> None:
    """Route ③: plan -> approve -> patch -> NG -> self-correction loop -> verify -> summary. The
    regeneration uses the same propose_for_item, so the evidence fix is what unblocks the repair
    loop too — proven here with the evidence-omitting model."""
    pool = _pool(tmp_path)
    storage, journal = _store(tmp_path, pool)
    proposal_service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=_llm_content_only)
    service = AtlasSelfCorrectionService(
        storage=storage,
        journal=journal,
        patch_proposal_service=proposal_service,
        auto_safe_apply_service=_FakeApply("applied"),
        auto_verification_service=_FakeVerify(fail_times=1),
    )

    out = service.run(
        AtlasSelfCorrectionRequest(
            pool_id="pool_1",
            item_id="item_1",
            run_id="run_1",
            verification_result={"status": "failed", "stderr_tail": "boom", "exit_code": 1},
            max_attempts=2,
        )
    )

    assert out.status == "recovered"
    assert out.final_verification_status == "passed"
