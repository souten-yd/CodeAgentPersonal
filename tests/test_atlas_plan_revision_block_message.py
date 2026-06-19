from __future__ import annotations

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def test_plan_revision_required_blocks_patch_before_llm_call(tmp_path) -> None:
    pool = AtlasPlanPool(
        pool_id="pool_block",
        root_goal="Create a page",
        metadata={"plan_revision_required": True, "planner_fallback": {"reason": "no_implementation_steps"}},
        items=[
            AtlasPlanItem(
                item_id="item_001",
                pool_id="pool_block",
                title="Create index",
                goal="Create index.html",
                description="Create an HTML file for the requested page.",
                item_type="implementation",
                status="ready",
                risk_level="low",
                target_files=["index.html"],
                metadata={
                    "action_type": "create",
                    "debug_review": {
                        "status": "analyzed",
                        "root_cause_category": "plan_item",
                        "proposed_fix": "Create the requested HTML file.",
                    },
                },
            )
        ],
    )
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    calls = {"count": 0}

    def llm(_system: str, _user: str) -> dict:
        calls["count"] += 1
        return {"proposed_content": "<!doctype html>"}

    service = AtlasPatchProposalService(journal=AtlasJournal(tmp_path), storage=storage, llm_json_fn=llm)
    result = service.propose_for_item(
        AtlasPatchProposalRequest(pool_id="pool_block", item_id="item_001", run_id="run_block", source_type="plan_item")
    )

    assert result.status == "blocked"
    assert "plan_revision_required_blocks_patch" in result.warnings
    assert "planner_fallback:no_implementation_steps" in result.warnings
    assert calls["count"] == 0


def test_completed_clean_clarification_reconciles_stale_revision_block(tmp_path) -> None:
    pool = AtlasPlanPool(
        pool_id="pool_reconciled",
        root_goal="Create a page",
        metadata={
            "plan_revision_required": True,
            "plan_revision_reason": "ambiguous_requirement_item_mapping",
            "clarification_replanning": {"status": "completed", "revision_id": "clar_rev_1"},
            "gate_rerun_performed_after_clarification": True,
            "gate_rerun_required_after_clarification": False,
            "plan_revision_required_after_clarification": False,
            "rerun_critique_gate_after_clarification": {"plan_revision_required": False},
        },
        items=[
            AtlasPlanItem(
                item_id="item_001",
                pool_id="pool_reconciled",
                title="Create index",
                goal="Create index.html",
                description="Create an HTML file for the requested page.",
                item_type="implementation",
                status="ready",
                risk_level="low",
                target_files=["index.html"],
                requirement_ids=["req_001"],
                metadata={"action_type": "create"},
            )
        ],
        requirements=[{"requirement_id": "req_001", "description": "Create index", "required": True}],
        requirement_item_map={"req_001": ["item_001"]},
    )
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    calls = {"count": 0}

    def llm(_system: str, _user: str) -> dict:
        calls["count"] += 1
        return {
            "target_files": ["index.html"],
            "proposed_content": "<!doctype html><title>Page</title>",
            "satisfied_requirement_ids": ["req_001"],
            "implemented_symbols": ["document"],
            "behavioral_cases": ["Page renders"],
            "verification_cases": ["Open index.html"],
            "risk_level": "low",
        }

    result = AtlasPatchProposalService(
        journal=AtlasJournal(tmp_path), storage=storage, llm_json_fn=llm
    ).propose_for_item(
        AtlasPatchProposalRequest(
            pool_id="pool_reconciled", item_id="item_001", run_id="run_reconciled", source_type="plan_item"
        )
    )

    assert result.status == "proposed"
    assert calls["count"] == 1
    reloaded = storage.load_pool("pool_reconciled")
    assert "plan_revision_required" not in reloaded.metadata
    assert reloaded.metadata["plan_revision_resolution_after_clarification"]["revision_id"] == "clar_rev_1"
