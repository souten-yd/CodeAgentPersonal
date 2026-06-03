from __future__ import annotations

from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.plan_schema import ImplementationStep, Plan


def test_implementation_step_goal_and_acceptance_reach_plan_pool_item() -> None:
    plan = Plan(
        plan_id="plan_goal_1",
        requirement_id="req_goal_1",
        user_goal="Hello World をレインボーで表示する HTML",
        done_definition=["レインボー表示が確認できること"],
        implementation_steps=[
            ImplementationStep(
                step_id="step_1",
                title="Create rainbow page",
                description="Hello World をレインボーで表示する index.html を作成する。",
                goal="Hello World のレインボー表示要件を満たす。",
                acceptance_criteria=[
                    "index.html に Hello World が表示されること",
                    "Hello World の文字がレインボー配色で表示されること",
                ],
                target_files=["index.html"],
                action_type="create",
                verification="ブラウザで Hello World のレインボー表示を確認する。",
            )
        ],
    )

    pool = AtlasPlanPoolBuilder().build_from_plan_payload(plan.model_dump(), root_goal=plan.user_goal, pool_id="pool_goal_1")
    item = pool.items[0]

    assert item.goal == "Hello World のレインボー表示要件を満たす。"
    assert item.description == "Hello World をレインボーで表示する index.html を作成する。"
    assert item.done_definition == [
        "index.html に Hello World が表示されること",
        "Hello World の文字がレインボー配色で表示されること",
    ]
