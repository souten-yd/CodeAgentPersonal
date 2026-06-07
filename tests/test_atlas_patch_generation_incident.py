from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_generation_state import reduce_patch_generation_state
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


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
