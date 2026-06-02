import json
from pathlib import Path

from agent.atlas_clarification_replanning_service import AtlasClarificationReplanningService
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _pool(tmp_path: Path) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_visual",
        root_goal="Create a Hello world visual artifact with rainbow blur animation.",
        status="approval_required",
        project_path=str(tmp_path / "ws"),
        items=[
            AtlasPlanItem(
                item_id="item_visual",
                pool_id="pool_visual",
                title="Create index.html",
                goal="Create the animated visual artifact.",
                item_type="implementation",
                status="approval_required",
                risk_level="medium",
                target_files=["index.html"],
                metadata={"action_type": "create"},
            )
        ],
        metadata={
            "clarification_answers": [
                {
                    "question_id": "clar_q_1",
                    "option_id": "custom",
                    "answer_text": "Use requestAnimationFrame to cycle colors with hsl and interpolate filter: blur with transition.",
                    "selected_option_impact": {
                        "plan_change_summary": "Add continuous visual animation logic.",
                        "implementation_scope": "requestAnimationFrame loop, HSL color cycle, filter: blur transition",
                        "risk_level": "low",
                        "gate_rerun_required": True,
                        "can_continue_after_answer": False,
                    },
                }
            ]
        },
    )


def test_clarification_revision_persists_concrete_visual_directives(tmp_path: Path):
    pool = _pool(tmp_path)

    result = AtlasClarificationReplanningService().revise_after_answers(pool)

    item = pool.items[0]
    directives = item.metadata["clarification_implementation_directives"]
    signals = {
        signal["signal"]
        for directive in directives
        for signal in directive["signals"]
    }
    assert {"requestAnimationFrame", "hsl", "filter_blur", "transition"}.issubset(signals)
    assert any("requestAnimationFrame" in change for change in item.expected_changes)
    assert any("HSL color mutation" in change for change in item.expected_changes)
    assert result["plan_revision_diff"]["clarification_implementation_directives"] == directives
    assert pool.metadata["revised_plan_snapshot"]["items"][0]["metadata"]["clarification_implementation_directives"] == directives


def test_revised_plan_adds_implementation_substeps_for_clarification_directives(tmp_path: Path):
    pool = _pool(tmp_path)
    AtlasClarificationReplanningService().revise_after_answers(pool)

    revised_plan = AtlasClarificationReplanningService._build_revised_plan(pool, pool.metadata["clarification_answers"], risk_raised=False)
    substeps = [
        step for step in revised_plan["implementation_steps"]
        if step.get("source") == "clarification_implementation_directive"
    ]

    assert len(revised_plan["implementation_steps"]) > len(pool.items)
    assert {step["clarification_signal"] for step in substeps} >= {"requestAnimationFrame", "hsl"}


def test_patch_proposal_payload_and_prompt_include_clarification_directives(tmp_path: Path):
    pool = _pool(tmp_path)
    AtlasClarificationReplanningService().revise_after_answers(pool)
    storage = AtlasPlanPoolStorage(tmp_path / "ca")
    journal = AtlasJournal(tmp_path / "ca", workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    captured: dict = {}

    def fake_llm(_system: str, user: str) -> dict:
        captured["user"] = json.loads(user)
        return {
            "target_files": ["index.html"],
            "proposed_content": "<!doctype html><script>requestAnimationFrame(() => {})</script>",
            "risk_level": "low",
        }

    svc = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=fake_llm)
    payload = svc.build_proposal_input(
        pool,
        pool.items[0],
        AtlasPatchProposalRequest(pool_id=pool.pool_id, item_id="item_visual", run_id="run_1", source_type="plan_item"),
    )

    assert payload["item"]["clarification_implementation_directives"]
    proposal = svc.generate_proposal_with_llm(payload)
    assert proposal.metadata["patch_content_available"] is True
    assert "clarification_directives" in captured["user"]
    assert any("requestAnimationFrame" in value for value in captured["user"]["clarification_directives"]["required_elements"])


def test_frontend_runtime_clarification_does_not_raise_high_risk(tmp_path: Path):
    pool = _pool(tmp_path)
    pool.items[0].target_files = ["index.html"]
    pool.metadata["clarification_answers"][0]["answer_text"] = "Repair the animation runtime loop with requestAnimationFrame."

    AtlasClarificationReplanningService().revise_after_answers(pool)

    assert pool.items[0].risk_level == "medium"
    assert pool.metadata["plan_revision_diff"]["risk_raised"] is False
