"""TFG-10 / Package 9A — Golden Patch Retrieval and Skill Distiller tests.

Proves the advisory accelerators stay advisory and evidence-bound:

- a matching successful patch is returned as advisory context;
- an unrelated patch is not returned above the confidence threshold;
- only accepted patches are indexed/distilled;
- a distilled skill includes evidence refs and scope and requires recurrence;
- disabling retrieval/distillation changes no correctness path.
"""
from __future__ import annotations

from agent.model_forge import (
    ChangeClass,
    GoldenPatch,
    GoldenPatchIndex,
    RetrievalQuery,
    distill_skills,
)
from agent.model_forge.execution_policy import (
    ExecutionPolicySelector,
    ModelCapabilityProfile,
)
from agent.model_forge.route_taxonomy import ForgeRoute


def _patch(patch_id, *, task="web_app", route=ForgeRoute.PATCH_DSL, model="m1",
           refs=None, outcome="accepted", evidence=None):
    return GoldenPatch(
        patch_id=patch_id, task_category=task, route=route, model_id=model,
        provider_id="local", affected_refs=refs or [], proof_outcome=outcome,
        evidence_refs=evidence or [f"ledger:{patch_id}"],
    )


def test_matching_patch_returned_as_advisory():
    index = GoldenPatchIndex()
    index.index_patch(_patch("p1", refs=["app/api.py", "app/models.py"]))
    query = RetrievalQuery(task_category="web_app", route=ForgeRoute.PATCH_DSL,
                           model_id="m1", affected_refs=["app/api.py"])
    out = index.retrieve(query)
    assert len(out) == 1
    assert out[0].patch.patch_id == "p1"
    assert out[0].advisory is True
    assert "task_category" in out[0].match_reasons
    assert out[0].confidence >= 0.5


def test_unrelated_patch_not_returned():
    index = GoldenPatchIndex()
    index.index_patch(_patch("p1", task="game_canvas", route=ForgeRoute.SLICED_IMPACT,
                             model="other", refs=["game/loop.js"]))
    query = RetrievalQuery(task_category="web_app", route=ForgeRoute.PATCH_DSL,
                           model_id="m1", affected_refs=["app/api.py"])
    assert index.retrieve(query) == []


def test_only_accepted_patches_indexed():
    index = GoldenPatchIndex()
    assert index.index_patch(_patch("good", outcome="accepted")) is True
    assert index.index_patch(_patch("bad", outcome="needs_repair")) is False
    assert len(index) == 1


def test_disabling_retrieval_returns_nothing():
    index = GoldenPatchIndex()
    index.index_patch(_patch("p1", refs=["app/api.py"]))
    query = RetrievalQuery(task_category="web_app", route=ForgeRoute.PATCH_DSL,
                           model_id="m1", affected_refs=["app/api.py"])
    assert index.retrieve(query, enabled=False) == []


def test_distilled_skill_requires_recurrence_and_evidence():
    # Two accepted patches in the same scope => one distilled skill.
    patches = [
        _patch("p1", refs=["app/api.py"], evidence=["ledger:p1"]),
        _patch("p2", refs=["app/models.py"], evidence=["ledger:p2"]),
        _patch("p3", task="repair", route=ForgeRoute.REPAIR_LOOP, evidence=["ledger:p3"]),
    ]
    skills = distill_skills(patches)
    # web_app/patch_dsl recurs twice -> skill; repair occurs once -> no skill.
    assert len(skills) == 1
    skill = skills[0]
    assert skill.task_category == "web_app"
    assert skill.route == ForgeRoute.PATCH_DSL
    assert skill.support == 2
    assert skill.advisory is True
    assert set(skill.evidence_refs) == {"ledger:p1", "ledger:p2"}
    assert skill.patch_refs == ["p1", "p2"]


def test_distillation_ignores_non_accepted_and_can_be_disabled():
    patches = [
        _patch("p1", evidence=["ledger:p1"]),
        _patch("p2", outcome="needs_repair", evidence=["ledger:p2"]),
    ]
    # Only one accepted patch => below min_support => no skill.
    assert distill_skills(patches) == []
    # Disabling returns nothing regardless.
    assert distill_skills(patches, enabled=False) == []


def test_retrieval_does_not_change_execution_policy():
    # ExecutionPolicy correctness must be identical whether or not retrieval ran.
    selector = ExecutionPolicySelector()
    profile = ModelCapabilityProfile(model_id="m1", capability_scores={"flag_reasoning": 0.9})
    baseline = selector.select(ChangeClass.MEDIUM, task_category="feature", model_profile=profile)

    index = GoldenPatchIndex()
    index.index_patch(_patch("p1", refs=["app/api.py"]))
    index.retrieve(RetrievalQuery(task_category="feature", affected_refs=["app/api.py"]))
    distill_skills([_patch("p1"), _patch("p2")])

    after = selector.select(ChangeClass.MEDIUM, task_category="feature", model_profile=profile)
    assert after.model_dump() == baseline.model_dump()
