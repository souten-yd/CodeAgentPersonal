"""6th: lower critique latency (single combined LLM call) + autopilot run returns clean HTTP errors."""
from __future__ import annotations

import tempfile

import pytest
from fastapi import HTTPException

from agent.adversarial_plan_critic import AdversarialPlanCritic


class _CountingLLM:
    def __init__(self, response):
        self.calls = 0
        self._response = response

    def __call__(self, system, user):
        self.calls += 1
        return self._response


def _plan():
    return {"implementation_steps": [{"title": "x"}], "selected_architecture": "a"}


def test_combined_mode_uses_single_llm_call():
    llm = _CountingLLM({"findings": [
        {"angle": "security", "severity": "high", "title": "missing auth", "recommendation": "add it"},
        {"angle": "maintainability", "severity": "warning", "title": "no tests"},
    ]})
    critic = AdversarialPlanCritic(llm_json_fn=llm, mode="combined")
    res = critic.critique(plan_summary=_plan(), requirement_summary={})
    assert llm.calls == 1  # 4 angles -> 1 call
    assert res.consensus_risk == "high"
    assert res.requires_revision is True
    angles = {f.angle for f in res.findings}
    assert "security" in angles and "maintainability" in angles


def test_per_angle_mode_calls_once_per_angle():
    llm = _CountingLLM({"findings": []})
    critic = AdversarialPlanCritic(llm_json_fn=llm, mode="per_angle")
    critic.critique(plan_summary=_plan(), requirement_summary={})
    assert llm.calls == len(critic.angles) == 4


def test_off_mode_skips_llm():
    llm = _CountingLLM({"findings": []})
    critic = AdversarialPlanCritic(llm_json_fn=llm, mode="off")
    res = critic.critique(plan_summary=_plan(), requirement_summary={})
    assert llm.calls == 0
    assert "critique_disabled" in res.warnings
    assert res.requires_revision is False


def test_env_default_is_combined(monkeypatch):
    monkeypatch.delenv("ATLAS_ADVERSARIAL_CRITIQUE_MODE", raising=False)
    critic = AdversarialPlanCritic(llm_json_fn=_CountingLLM({"findings": []}))
    assert critic.mode == "combined"


def test_no_llm_skips_gracefully():
    res = AdversarialPlanCritic(llm_json_fn=None).critique(plan_summary={}, requirement_summary={})
    assert "critique_skipped_no_llm" in res.warnings


def _autopilot_client():
    import main
    from fastapi.testclient import TestClient

    main.app.state.atlas_ca_data_dir = tempfile.mkdtemp()
    return TestClient(main.app)


def test_autopilot_run_missing_pool_returns_404():
    c = _autopilot_client()
    r = c.post("/api/atlas/multi-item-autopilot/run", json={"pool_id": "pool_does_not_exist", "workspace_id": "default"})
    assert r.status_code == 404, r.text
    assert r.json()["detail"]["error"] == "pool_not_found"
