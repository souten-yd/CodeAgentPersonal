from __future__ import annotations

from pathlib import Path

from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage

# Reproduces a real bug: a plan step whose goal is already fully implemented by an EARLIER step's
# code in the same shared target file (common for a single-file app built up over several steps)
# used to fail forever. The model correctly returns no edits/content -- there is nothing left to
# add -- but the pipeline treated that honest response as content_missing/semantic_evidence_missing
# and retried 5 times before failing the item, permanently blocking the run on a step whose goal
# was, in fact, already met.

_GOAL = "Set up the widget counter and render its initial value on load."
_REQ_DESCRIPTION = "Counter element renders its initial value on load"
_ALREADY_DONE_CONTENT = (
    "<html><body>\n"
    "<div id=\"counter\">0</div>\n"
    "<script>\n"
    "// counter element renders its initial value on load\n"
    "function initCounter() { document.getElementById('counter').textContent = '0'; }\n"
    "window.onload = initCounter;\n"
    "</script>\n"
    "</body></html>\n"
)


def _item() -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id="item_001",
        pool_id="pool_1",
        title="Render initial counter",
        goal=_GOAL,
        description="Initialize the counter element and display its starting value on page load.",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["index.html"],
        requirement_ids=["req_counter"],
        acceptance_criteria=[_REQ_DESCRIPTION],
        metadata={"action_type": "update"},
    )


def _pool(tmp_path: Path, item: AtlasPlanItem) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_1",
        root_goal="Build a widget page",
        project_path=str(tmp_path),
        status="ready",
        requirements=[{"requirement_id": "req_counter", "description": _REQ_DESCRIPTION, "required": True}],
        requirement_item_map={"req_counter": ["item_001"]},
        items=[item],
        completed_item_ids=[],
    )


def _service(tmp_path: Path, pool: AtlasPlanPool, llm) -> AtlasPatchProposalService:
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm)


def _build_payload(tmp_path: Path, item: AtlasPlanItem, pool: AtlasPlanPool, llm):
    service = _service(tmp_path, pool, llm)
    payload = service.build_proposal_input(
        pool, item,
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item"),
    )
    return service, payload


def test_empty_response_is_accepted_when_existing_content_already_covers_the_goal(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(_ALREADY_DONE_CONTENT, encoding="utf-8")
    item = _item()
    pool = _pool(tmp_path, item)
    # An honest model correctly finds nothing left to add.
    llm = lambda system, user: {"target_files": ["index.html"], "edits": [], "risk_level": "low"}
    service, payload = _build_payload(tmp_path, item, pool, llm)

    proposal = service._generate_proposal_with_llm_core(payload)
    meta = proposal.metadata or {}

    assert meta.get("generation_failed") is not True
    assert meta.get("already_satisfied_no_op") is True
    assert meta.get("patch_content_available") is True
    assert meta.get("semantic_validation", {}).get("status") == "passed"
    assert "req_counter" in (meta.get("satisfied_requirement_ids") or [])


def test_empty_response_still_fails_when_goal_is_genuinely_unmet(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><body>\n<!-- nothing implemented yet -->\n</body></html>\n", encoding="utf-8")
    item = _item()
    pool = _pool(tmp_path, item)
    llm = lambda system, user: {"target_files": ["index.html"], "edits": [], "risk_level": "low"}
    service, payload = _build_payload(tmp_path, item, pool, llm)

    proposal = service._generate_proposal_with_llm_core(payload)
    meta = proposal.metadata or {}

    assert meta.get("already_satisfied_no_op") is not True
    assert meta.get("generation_failed") is True


def test_already_satisfied_no_op_applies_as_identity_content() -> None:
    executor = AtlasFileSafeApplyExecutor.__new__(AtlasFileSafeApplyExecutor)
    metadata = {"already_satisfied_no_op": True, "patch_content_available": True}

    result = executor._resolve_content_from_metadata(
        metadata, current_text=_ALREADY_DONE_CONTENT, target_exists=True, file_path="index.html",
    )

    assert result == {"status": "ok", "content": _ALREADY_DONE_CONTENT, "mode": "no_op_already_satisfied"}


def test_already_satisfied_no_op_ignored_without_existing_target() -> None:
    executor = AtlasFileSafeApplyExecutor.__new__(AtlasFileSafeApplyExecutor)
    metadata = {"already_satisfied_no_op": True}

    result = executor._resolve_content_from_metadata(
        metadata, current_text="", target_exists=False, file_path="index.html",
    )

    assert result == {"status": "blocked", "reason": "content_missing"}
