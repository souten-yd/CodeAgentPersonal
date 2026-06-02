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
