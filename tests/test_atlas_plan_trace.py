from __future__ import annotations

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_plan_trace import PlanTrace, read_plan_trace, summarize_root_cause


def test_plan_trace_records_root_cause_and_detail_toggle(tmp_path) -> None:
    trace = PlanTrace(data_root=tmp_path, pool_id="p1", run_id="r1", detail_enabled=False)
    trace.record(
        stage="planner_llm",
        decision="fallback",
        reason="no_implementation_steps",
        detail={"raw_output_tail": "hidden"},
    )
    trace.record(stage="plan_depth_gate", decision="block", reason="no_implementation_items")
    records = read_plan_trace(tmp_path, pool_id="p1", run_id="r1")

    assert [r["stage"] for r in records] == ["planner_llm", "plan_depth_gate"]
    assert "detail" not in records[0]
    assert summarize_root_cause(records) == {
        "root_cause_stage": "planner_llm",
        "root_cause_reason": "no_implementation_steps",
    }

    detailed = PlanTrace(data_root=tmp_path, pool_id="p2", run_id="r2", detail_enabled=True)
    detailed.record(
        stage="planner_llm",
        decision="fallback",
        reason="no_implementation_steps",
        detail={"raw_output_tail": "visible", "token": "secret-value"},
    )
    detailed_records = read_plan_trace(tmp_path, pool_id="p2", run_id="r2")
    assert detailed_records[0]["detail"]["raw_output_tail"] == "visible"
    assert detailed_records[0]["detail"]["token"] == "[masked]"


def test_patch_block_records_llm_not_called(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_PLAN_TRACE", "1")
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path)
    pool = AtlasPlanPool(
        pool_id="p1",
        root_goal="g",
        metadata={"plan_revision_required": True},
        items=[
            AtlasPlanItem(
                item_id="i1",
                pool_id="p1",
                title="Create file",
                goal="Create file",
                description="Create an implementation file for the user request",
                item_type="implementation",
                target_files=["index.html"],
            )
        ],
    )
    storage.save_pool(pool)
    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=lambda _s, _u: {"ok": True})

    result = service.propose_for_item(AtlasPatchProposalRequest(pool_id="p1", item_id="i1", run_id="r1"))
    records = read_plan_trace(tmp_path, pool_id="p1", run_id="r1")

    assert result.status == "blocked"
    assert records[-1]["stage"] == "patch_proposal"
    assert records[-1]["reason"] == "plan_revision_required_blocks_patch"
    assert records[-1]["detail"]["llm_called"] is False
