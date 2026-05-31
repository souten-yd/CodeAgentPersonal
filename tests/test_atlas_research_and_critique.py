"""Phase 3: research-first conductor + adversarial plan critique."""
from __future__ import annotations

from agent.adversarial_plan_critic import AdversarialPlanCritic
from agent.research_conductor import ResearchConductor


def test_research_conductor_returns_findings_and_prompt_text():
    def fake_llm(system, user):
        return {
            "relevant_files": ["app/main.py", "app/api/x.py"],
            "existing_patterns": ["reuse AtlasJournal for events"],
            "key_findings": ["routes are registered in app/server.py"],
            "risks": ["shared app.state executor pinned to cwd"],
            "recommended_approach": "extend the existing router",
        }
    out = ResearchConductor(llm_json_fn=fake_llm).conduct(
        user_input="add endpoint", interpreted_goal="add endpoint", repository_context="files...", nexus_text="")
    assert out.relevant_files == ["app/main.py", "app/api/x.py"]
    text = out.to_prompt_text()
    assert "Recommended approach" in text and "app/main.py" in text


def test_research_conductor_degrades_without_llm():
    out = ResearchConductor(llm_json_fn=None).conduct(
        user_input="x", interpreted_goal="x", repository_context="", nexus_text="")
    assert "research_skipped_no_llm" in out.warnings
    assert out.to_prompt_text() == ""


def test_research_conductor_handles_llm_exception():
    def boom(system, user):
        raise RuntimeError("backend down")
    out = ResearchConductor(llm_json_fn=boom).conduct(
        user_input="x", interpreted_goal="x", repository_context="", nexus_text="")
    assert any(w.startswith("research_failed") for w in out.warnings)


def test_critic_aggregates_worst_risk_and_requires_revision():
    def fake_llm(system, user):
        # Return a high finding for one angle, nothing for others.
        import json
        angle = json.loads(user).get("angle")
        if angle == "security":
            return {"findings": [{"severity": "high", "title": "no auth check", "detail": "endpoint open", "recommendation": "add auth"}], "angle_risk": "high", "requires_revision": True}
        return {"findings": [], "angle_risk": "low", "requires_revision": False}
    # per_angle mode: the mock keys off the per-call angle field (one LLM call per angle).
    res = AdversarialPlanCritic(llm_json_fn=fake_llm, mode="per_angle").critique(
        plan_summary={"implementation_steps": []}, requirement_summary={})
    assert res.consensus_risk == "high"
    assert res.requires_revision is True
    assert len(res.findings) == 1
    assert res.findings[0].angle == "security"
    assert set(res.angles_evaluated) == {"security", "maintainability", "missing_steps", "requirement_alignment"}


def test_critic_clean_plan_low_risk_no_revision():
    def fake_llm(system, user):
        return {"findings": [], "angle_risk": "low", "requires_revision": False}
    res = AdversarialPlanCritic(llm_json_fn=fake_llm).critique(plan_summary={}, requirement_summary={})
    assert res.consensus_risk == "low"
    assert res.requires_revision is False
    assert res.findings == []


def test_critic_degrades_without_llm():
    res = AdversarialPlanCritic(llm_json_fn=None).critique(plan_summary={}, requirement_summary={})
    assert "critique_skipped_no_llm" in res.warnings
    assert res.findings == []
