from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _item(*, target_files=None, requirement_ids=None) -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id="item_001",
        pool_id="pool_1",
        title="Implement score",
        goal="Score increments",
        description="Implement score increments with persisted state.",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=target_files or ["app.py"],
        requirement_ids=requirement_ids or ["req_score"],
        acceptance_criteria=["Score increments"],
        verification_contract={"contract_id": "pytest", "signals": ["score"]},
        preserve_behaviors=["Keep reset"],
        metadata={"action_type": "update"},
    )


def _pool(tmp_path: Path, item: AtlasPlanItem, *, completed: bool = False) -> AtlasPlanPool:
    prior = AtlasPlanItem(
        item_id="item_done",
        pool_id="pool_1",
        title="Completed prior",
        goal="Render existing widget",
        status="completed" if completed else "ready",
        target_files=["done.py"],
        requirement_ids=["req_done"],
        metadata={"safe_apply": {"changed_files": ["done.py"]}},
    )
    return AtlasPlanPool(
        pool_id="pool_1",
        root_goal="Build score widget",
        original_user_request="Create score widget and keep reset.",
        selected_architecture="Use existing score module",
        global_constraints=["No remote push"],
        requirements=[
            {"requirement_id": "req_score", "description": "Score increments", "required": True},
            {"requirement_id": "req_done", "description": "Existing widget rendered", "required": True},
        ],
        preserve_behaviors=["Keep reset"],
        requirement_item_map={"req_score": ["item_001"], "req_done": ["item_done"]},
        project_path=str(tmp_path),
        status="ready",
        items=[prior, item],
        completed_item_ids=["item_done"] if completed else [],
        metadata={
            "requirement_trace": [
                {"requirement_id": "req_score", "description": "Score increments", "required": True},
                {"requirement_id": "req_done", "description": "Existing widget rendered", "required": True},
            ]
        },
    )


def _service(tmp_path: Path, pool: AtlasPlanPool, llm=None) -> tuple[AtlasPatchProposalService, AtlasPlanPoolStorage]:
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=llm), storage


def test_codegen_proposal_input_contains_full_context_and_multifile_contents(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def score():\n    return 1\n", encoding="utf-8")
    (tmp_path / "style.css").write_text(".score { color: blue; }\n", encoding="utf-8")
    item = _item(target_files=["app.py", "style.css"])
    pool = _pool(tmp_path, item, completed=True)
    service, _storage = _service(tmp_path, pool)

    payload = service.build_proposal_input(
        pool,
        item,
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item"),
    )

    assert payload["root_goal"] == "Build score widget"
    assert payload["original_user_request"] == "Create score widget and keep reset."
    assert payload["selected_architecture"] == "Use existing score module"
    assert payload["global_constraints"] == ["No remote push"]
    assert [r["requirement_id"] for r in payload["all_requirements"]] == ["req_score", "req_done"]
    assert [r["requirement_id"] for r in payload["requirements_for_this_item"]] == ["req_score"]
    assert [r["requirement_id"] for r in payload["already_satisfied_requirements"]] == ["req_done"]
    assert payload["completed_item_summaries"][0]["item_id"] == "item_done"
    assert payload["current_target_contents"]["app.py"]["content"].startswith("def score")
    assert payload["current_target_contents"]["style.css"]["content"].startswith(".score")
    assert payload["base_file_revisions"]["app.py"] != "absent"
    assert payload["preserve_behaviors"] == ["Keep reset"]


def test_codegen_semantic_validation_retries_until_evidence_is_complete(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def score():\n    return 1\n", encoding="utf-8")
    calls: list[int] = []

    def llm(_system: str, _user: str) -> dict:
        calls.append(1)
        if len(calls) == 1:
            return {"target_files": ["app.py"], "proposed_content": "def score():\n    return 2\n"}
        return {
            "target_files": ["app.py"],
            "edits": [{"old_string": "def score():\n    return 1", "new_string": "def score():\n    return 2  # score increments"}],
            "satisfied_requirement_ids": ["req_score"],
            "implemented_symbols": ["score"],
            "behavioral_cases": ["Score increments"],
            "verification_cases": ["pytest score"],
        }

    item = _item()
    pool = _pool(tmp_path, item)
    service, storage = _service(tmp_path, pool, llm=llm)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item", run_id="run_1")
    )

    assert len(calls) == 2
    assert result.metadata["patch_content_available"] is True
    reloaded = storage.load_pool("pool_1").get_item("item_001")
    assert reloaded is not None
    assert reloaded.metadata["edits"][0]["new_string"].endswith("score increments")
    assert reloaded.metadata["patch_proposal"]["metadata"]["semantic_validation"]["status"] == "passed"


def test_codegen_rejects_requirement_ids_not_authorized_by_item(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def score():\n    return 1\n", encoding="utf-8")

    def llm(_system: str, _user: str) -> dict:
        return {
            "target_files": ["app.py"],
            "edits": [{"old_string": "return 1", "new_string": "return 2  # score increments"}],
            "satisfied_requirement_ids": ["req_other"],
            "implemented_symbols": ["score"],
            "behavioral_cases": ["Score increments"],
            "verification_cases": ["pytest score"],
        }

    item = _item()
    pool = _pool(tmp_path, item)
    service, storage = _service(tmp_path, pool, llm=llm)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item", run_id="run_1")
    )

    assert result.metadata["patch_content_available"] is False
    assert "semantic_validation_failed" in (result.proposal.warnings if result.proposal else result.warnings)
    reloaded = storage.load_pool("pool_1").get_item("item_001")
    assert reloaded is not None
    assert "edits" not in reloaded.metadata


def test_codegen_rejects_incomplete_multifile_response(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def score():\n    return 1\n", encoding="utf-8")
    (tmp_path / "style.css").write_text(".score { color: blue; }\n", encoding="utf-8")

    def llm(_system: str, _user: str) -> dict:
        return {
            "target_files": ["app.py", "style.css"],
            "file_changes": [{"path": "app.py", "action_type": "update", "proposed_content": "def score():\n    return 2\n"}],
            "satisfied_requirement_ids": ["req_score"],
            "implemented_symbols": ["score"],
            "behavioral_cases": ["Score increments"],
            "verification_cases": ["pytest score"],
        }

    item = _item(target_files=["app.py", "style.css"])
    pool = _pool(tmp_path, item)
    service, storage = _service(tmp_path, pool, llm=llm)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item", run_id="run_1")
    )

    assert result.metadata["patch_content_available"] is False
    assert result.proposal is not None
    assert "multi_file_content_missing:style.css" in result.proposal.metadata["semantic_validation"]["reasons"]
    reloaded = storage.load_pool("pool_1").get_item("item_001")
    assert reloaded is not None
    assert "file_changes" not in reloaded.metadata


def test_codegen_final_self_review_failure_returns_no_content(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def score():\n    return 1\n", encoding="utf-8")

    def llm(_system: str, _user: str) -> dict:
        return {
            "target_files": ["app.py"],
            "proposed_content": "def score(:\n    return 'score increments'\n",
            "satisfied_requirement_ids": ["req_score"],
            "implemented_symbols": ["score"],
            "behavioral_cases": ["Score increments"],
            "verification_cases": ["pytest score"],
        }

    item = _item()
    pool = _pool(tmp_path, item)
    service, storage = _service(tmp_path, pool, llm=llm)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item", run_id="run_1")
    )

    assert result.metadata["patch_content_available"] is False
    assert result.proposal is not None
    assert "self_review_findings_unresolved" in result.proposal.warnings
    assert result.proposal.metadata["self_review"]["status"] == "failed"
    reloaded = storage.load_pool("pool_1").get_item("item_001")
    assert reloaded is not None
    assert "proposed_content" not in reloaded.metadata


def test_codegen_rejects_oversized_content_without_truncating(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def score():\n    return 1\n", encoding="utf-8")
    oversized = "x" * (AtlasPatchProposalService.MAX_PROPOSED_CONTENT_CHARS + 1)

    def llm(_system: str, _user: str) -> dict:
        return {
            "target_files": ["app.py"],
            "proposed_content": oversized,
            "satisfied_requirement_ids": ["req_score"],
            "implemented_symbols": ["score"],
            "behavioral_cases": ["Score increments"],
            "verification_cases": ["pytest score"],
        }

    item = _item()
    pool = _pool(tmp_path, item)
    service, storage = _service(tmp_path, pool, llm=llm)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item", run_id="run_1")
    )

    assert result.metadata["patch_content_available"] is False
    assert result.proposal is not None
    assert "content_too_large" in result.proposal.metadata["semantic_validation"]["reasons"]
    reloaded = storage.load_pool("pool_1").get_item("item_001")
    assert reloaded is not None
    assert "proposed_content" not in reloaded.metadata


def test_codegen_rejects_disconnected_multifile_artifact(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><main id='app'></main>\n", encoding="utf-8")
    (tmp_path / "game.js").write_text("export function score(){ return 1 }\n", encoding="utf-8")

    def llm(_system: str, _user: str) -> dict:
        return {
            "target_files": ["index.html", "game.js"],
            "file_changes": [
                {"path": "index.html", "action_type": "update", "proposed_content": "<!doctype html><main id='app'>Score increments</main>\n"},
                {"path": "game.js", "action_type": "update", "proposed_content": "export function score(){ return 2 }\n"},
            ],
            "satisfied_requirement_ids": ["req_score"],
            "implemented_symbols": ["score"],
            "behavioral_cases": ["Score increments"],
            "verification_cases": ["browser score"],
        }

    item = _item(target_files=["index.html", "game.js"])
    pool = _pool(tmp_path, item)
    service, storage = _service(tmp_path, pool, llm=llm)

    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_1", item_id="item_001", source_type="plan_item", run_id="run_1")
    )

    assert result.metadata["patch_content_available"] is False
    assert result.proposal is not None
    assert "disconnected_artifact:game.js" in result.proposal.metadata["semantic_validation"]["reasons"]
    reloaded = storage.load_pool("pool_1").get_item("item_001")
    assert reloaded is not None
    assert "file_changes" not in reloaded.metadata
