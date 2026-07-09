from pathlib import Path

from agent.atlas_clarification_replanning_service import AtlasClarificationReplanningService
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _pool(tmp_path: Path, *, plan_revision_required: bool = True) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_clar",
        root_goal="Build a small tool.",
        status="approval_required",
        project_path=str(tmp_path / "ws"),
        items=[
            AtlasPlanItem(
                item_id="item_1",
                pool_id="pool_clar",
                title="Create index.html",
                goal="Create the tool.",
                item_type="implementation",
                status="approval_required",
                risk_level="low",
                target_files=["index.html"],
                metadata={"action_type": "create"},
            )
        ],
        metadata={
            # Simulates a plan that previously tripped the critique/quality gate (the initial
            # plan-creation path sets this True — see app/api/atlas_pipeline.py).
            "plan_revision_required": plan_revision_required,
            "clarification_answers": [
                {
                    "question_id": "clar_q_1",
                    "option_id": "revise_0",
                    "answer_text": "Use requestAnimationFrame for the render loop.",
                }
            ],
        },
    )


def test_revise_after_answers_clears_stale_plan_revision_required_flag(tmp_path: Path):
    # Reproduces a real stuck-forever bug: nothing else in the codebase ever clears
    # pool.metadata["plan_revision_required"] once a prior gate pass set it True. A user who
    # answers every clarification question and gets a clean gate re-evaluation (no findings,
    # no risk raised) must not stay permanently blocked from patch generation.
    pool = _pool(tmp_path, plan_revision_required=True)

    result = AtlasClarificationReplanningService().revise_after_answers(pool)

    assert result["status"] != "waiting_for_critical_decision"
    assert pool.metadata["plan_revision_required"] is False


def test_revise_after_answers_unblocks_propose_for_item(tmp_path: Path):
    # The cleared flag must actually unblock propose_for_item's own early-return gate check
    # (agent/atlas_patch_proposal_service.py), not just look right on the pool object in isolation.
    pool = _pool(tmp_path, plan_revision_required=True)
    AtlasClarificationReplanningService().revise_after_answers(pool)
    assert bool(pool.metadata.get("plan_revision_required")) is False

    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca", workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=None)
    result = svc.propose_for_item(
        AtlasPatchProposalRequest(pool_id=pool.pool_id, item_id="item_1", run_id="run_1", source_type="plan_item"),
    )
    assert "plan_revision_required_blocks_patch" not in result.warnings


def test_propose_for_item_still_blocks_when_flag_stays_true(tmp_path: Path):
    # Sanity check for the test above: confirms propose_for_item really does gate on this flag,
    # so a passing test above is meaningful and not just because the gate is a no-op.
    pool = _pool(tmp_path, plan_revision_required=True)
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca", workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=None)
    result = svc.propose_for_item(
        AtlasPatchProposalRequest(pool_id=pool.pool_id, item_id="item_1", run_id="run_1", source_type="plan_item"),
    )
    assert "plan_revision_required_blocks_patch" in result.warnings
