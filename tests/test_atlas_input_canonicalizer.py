from __future__ import annotations

from agent.atlas_input_canonicalizer import AtlasInputCanonicalizer, contains_cjk, ensure_english_text
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.planner_phase1 import PlannerPhase1
from agent.requirement_schema import RequirementDefinition


JA_FPS_PROMPT = """007ゴールデンアイみたいなファーストパーソンシューティングゲームをHTMLで作って。
舞台は宇宙ステーション。
ハンドガン、ショットガン、ロケットランチャー。
弾は無限。
敵は宇宙人。"""


def test_canonicalization_extracts_japanese_fps_requirements_in_english() -> None:
    spec = AtlasInputCanonicalizer().canonicalize(JA_FPS_PROMPT)

    assert spec.source_language == "ja"
    assert spec.canonical_language == "en"
    assert not contains_cjk(spec.canonical_request_en)
    assert [req.id for req in spec.canonical_requirements] == [f"req_{i:03d}" for i in range(1, 8)]
    canonical_text = " ".join(req.canonical_text_en for req in spec.canonical_requirements)
    assert not contains_cjk(canonical_text)
    for expected in (
        "first-person shooter",
        "HTML",
        "space station",
        "handgun",
        "shotgun",
        "rocket launcher",
        "unlimited ammunition",
        "alien enemies",
    ):
        assert expected.lower() in canonical_text.lower()
    assert any(req.raw_text for req in spec.canonical_requirements)


def test_mixed_language_canonicalization_outputs_english_only() -> None:
    prompt = "HTMLでFPSを作って。space stationが舞台で、weaponはhandgun, shotgun, rocket launcher。敵は宇宙人。"

    spec = AtlasInputCanonicalizer().canonicalize(prompt)

    assert spec.source_language == "mixed"
    assert not contains_cjk(spec.canonical_request_en)
    assert spec.canonical_requirements
    assert all(not contains_cjk(req.canonical_text_en) for req in spec.canonical_requirements)


def test_requirement_mapping_uses_canonical_english_requirements() -> None:
    spec = AtlasInputCanonicalizer().canonicalize(JA_FPS_PROMPT)
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {
            "requirements": [req.model_dump() for req in spec.canonical_requirements],
            "implementation_steps": [
                {
                    "step_id": "step_space",
                    "title": "Build the space station scene",
                    "description": "Create an HTML retro FPS level set in a space station.",
                    "action_type": "create",
                    "target_files": ["index.html"],
                    "acceptance_criteria": ["The browser game opens in a space station environment."],
                    "verification_contract": {"contract_id": "browser_smoke"},
                },
                {
                    "step_id": "step_weapons",
                    "title": "Implement weapons, ammunition, and aliens",
                    "description": "Add handgun, shotgun, rocket launcher, unlimited ammunition, alien enemies, combat, damage, and defeat feedback.",
                    "action_type": "update",
                    "target_files": ["game.js"],
                    "acceptance_criteria": ["Weapons and alien combat are playable."],
                    "verification_contract": {"contract_id": "browser_smoke"},
                },
            ],
        },
        root_goal=spec.canonical_request_en,
        pool_id="pool_canon",
        automation_level="plan_then_ask",
    )

    assert "plan_revision_required" not in pool.metadata
    assert pool.plan_quality["ok"] is True
    for req in spec.canonical_requirements:
        assert pool.requirement_item_map.get(req.id), req.id


def test_ensure_english_plan_text_removes_known_cjk_terms() -> None:
    text = ensure_english_text("ゴール: 宇宙ステーションで敵を倒す")

    assert not contains_cjk(text)
    assert "space station" in text
    assert "enemy" in text


def test_planner_output_cjk_is_normalized_before_planpool() -> None:
    spec = AtlasInputCanonicalizer().canonicalize(JA_FPS_PROMPT)

    def fake_llm(_system_prompt: str, _user_prompt: str) -> dict:
        return {
            "user_goal": "宇宙ステーションで敵を倒すFPSを作る",
            "requirement_summary": "ハンドガンと敵を実装する",
            "implementation_steps": [
                {
                    "title": "宇宙ステーションを作る",
                    "description": "敵とハンドガンを追加する",
                    "goal": "宇宙人を倒す",
                    "acceptance_criteria": ["敵を倒せる"],
                    "action_type": "create",
                    "risk_level": "low",
                    "verification": "検証する",
                    "rollback": "戻す",
                    "target_files": ["index.html"],
                }
            ],
            "test_plan": ["検証する"],
            "rollback_plan": ["戻す"],
            "destructive_change_detected": False,
            "requires_user_confirmation": False,
        }

    requirement = RequirementDefinition(
        requirement_id="req_test",
        source_task_id="task_test",
        user_input=spec.canonical_request_en,
        raw_user_input=JA_FPS_PROMPT,
        interpreted_goal=spec.canonical_request_en,
        canonical_task_spec=spec.model_dump(),
    )

    plan = PlannerPhase1(fake_llm).build_plan(
        requirement=requirement,
        planning_mode="standard",
        prompt="Return JSON only.",
        nexus_context={},
        repository_context="",
    )

    joined = " ".join([
        plan.user_goal,
        plan.requirement_summary,
        *plan.test_plan,
        *plan.rollback_plan,
        *[step.title for step in plan.implementation_steps],
        *[step.description for step in plan.implementation_steps],
        *[criterion for step in plan.implementation_steps for criterion in step.acceptance_criteria],
    ])
    assert not contains_cjk(joined)
