"""6th: strategic plan summary persisted on pool.metadata for the Claude/Codex-style plan card."""
from __future__ import annotations

import tempfile

from fastapi.testclient import TestClient

import main


def _client():
    main.app.state.atlas_ca_data_dir = tempfile.mkdtemp()
    main.app.state.atlas_llm_json_fn = None  # deterministic fallback planner
    return TestClient(main.app)


def _payload():
    return {
        "implementation_steps": [
            {
                "title": "Create index.html",
                "description": "Write a minimal HTML page that prints Hello World in an h1.",
                "goal": "Expose a visible Hello World page.",
                "acceptance_criteria": ["h1 contains Hello World"],
                "action_type": "create",
                "target_files": ["index.html"],
                "risk_level": "low",
                "verification": "open in browser",
                "rollback": "delete index.html",
            }
        ],
        "selected_architecture": "Static single-file page",
        "architecture_options": ["Static page", "SPA"],
        "risks": ["none"],
        "test_plan": ["visual check"],
        "done_definition": ["page shows Hello World"],
    }


def test_strategic_plan_in_create_and_get():
    c = _client()
    r = c.post("/api/atlas/plan-pools?sync=1", json={"input": "hello world html", "plan_payload": _payload()})
    assert r.status_code == 200, r.text
    body = r.json()
    pid = body["pool_id"]
    sp = (body.get("plan_pool", {}).get("metadata", {}) or {}).get("strategic_plan")
    assert isinstance(sp, dict)
    assert sp.get("goal")
    # steps populated (from items fallback in the plan_payload path)
    steps = sp.get("steps") or []
    assert len(steps) == 1
    assert steps[0]["title"] == "Create index.html"
    assert steps[0]["goal"] == "Expose a visible Hello World page."
    assert steps[0]["acceptance_criteria"] == ["h1 contains Hello World"]
    assert steps[0]["target_files"] == ["index.html"]

    # GET returns it too (survives via pool.metadata)
    g = c.get(f"/api/atlas/plan-pools/{pid}").json()
    gsp = (g.get("metadata", {}) or {}).get("strategic_plan")
    assert isinstance(gsp, dict) and len(gsp.get("steps", [])) == 1


def test_strategic_plan_summary_bounds_and_shape():
    from app.api.atlas_pipeline import _build_strategic_plan_summary

    class _Item:
        title = "t"; description = "d"; goal = "g"; target_files = ["a.py"]; risk_level = "low"
        done_definition = ["dd"]; rollback_plan = ["rb"]; depends_on = ["prev"]; status = "ready"; errors = []
        item_id = "item_1"; metadata = {"action_type": "update", "phase": "planning", "progress": "1/2"}

    class _Pool:
        root_goal = "root goal"
        items = [_Item() for _ in range(50)]  # exceeds the 30 cap

    plan = {
        "user_goal": "do the thing",
        "selected_architecture": "arch",
        "implementation_steps": [
            {"title": f"s{i}", "description": "x" * 1000, "target_files": ["f.py"], "action_type": "create",
             "risk_level": "low", "goal": "step goal", "acceptance_criteria": "step accepted",
             "verification": "v", "rollback": "r", "depends_on": ["previous"]}
            for i in range(50)
        ],
        "research_findings": {"recommended_approach": "reuse X", "key_findings": ["kf"], "relevant_files": ["a.py"], "risks": []},
        "adversarial_critique": {"consensus_risk": "high", "requires_revision": True,
                                  "findings": [{"angle": "security", "severity": "high", "title": "gap", "recommendation": "fix"}]},
    }
    review = {"overall_risk": "medium", "summary": "looks ok", "recommended_next_action": "proceed",
              "findings": [{"title": "f", "severity": "warning", "category": "other", "recommendation": "rec"}]}
    sp = _build_strategic_plan_summary(requirement={"interpreted_goal": "G"}, plan=plan, review_result=review, pool=_Pool())
    assert sp["goal"] == "G"
    assert len(sp["steps"]) == 30  # capped
    assert len(sp["steps"][0]["description"]) <= 600  # truncated
    assert sp["steps"][0]["goal"] == "step goal"
    assert sp["steps"][0]["acceptance_criteria"] == ["step accepted"]
    assert sp["steps"][0]["dependencies"] == ["previous"]
    assert sp["selected_architecture"] == "arch"
    assert sp["review"]["overall_risk"] == "medium"
    assert sp["research"]["recommended_approach"] == "reuse X"
    assert sp["adversarial_critique"]["requires_revision"] is True
    assert sp["adversarial_critique"]["findings"][0]["angle"] == "security"


def test_strategic_plan_summary_fallback_preserves_step_detail_fields():
    from app.api.atlas_pipeline import _build_strategic_plan_summary

    class _Item:
        item_id = "item_001"
        title = "Legacy step"
        description = "Legacy description"
        goal = "Legacy goal"
        target_files = ["legacy.py"]
        risk_level = "medium"
        done_definition = ["legacy acceptance"]
        rollback_plan = ["restore legacy.py"]
        depends_on = ["item_000"]
        status = "queued"
        errors = ["waiting for dependency"]
        metadata = {"action_type": "update", "phase": "planning", "progress": "0/1"}

    class _Pool:
        root_goal = "root goal"
        items = [_Item()]

    sp = _build_strategic_plan_summary(requirement={}, plan={}, review_result={}, pool=_Pool())
    step = sp["steps"][0]
    assert step["id"] == "item_001"
    assert step["index"] == 1
    assert step["title"] == "Legacy step"
    assert step["goal"] == "Legacy goal"
    assert step["acceptance_criteria"] == ["legacy acceptance"]
    assert step["verification"] == "legacy acceptance"
    assert step["rollback"] == "restore legacy.py"
    assert step["target_files"] == ["legacy.py"]
    assert step["action_type"] == "update"
    assert step["risk_level"] == "medium"
    assert step["dependencies"] == ["item_000"]
    assert step["blockers"] == ["waiting for dependency"]
    assert step["status"] == "queued"
    assert step["phase"] == "planning"
    assert step["progress"] == "0/1"


def test_strategic_plan_surfaces_planner_bridge_fallback_reason() -> None:
    """When the real planner failed and the generic fallback pool was substituted, the plan card must
    state why — otherwise the user sees only a tiny 3-step plan that dead-ends at safe_apply_not_applied.
    """
    from app.api.atlas_pipeline import _build_strategic_plan_summary

    class _Pool:
        root_goal = "rainbow hello world"
        warnings = ["planner_bridge_failed", "real_planner_unavailable", "fallback_plan_items_generated"]
        metadata = {"planner_bridge_reason": "KeyError: 'implementation_steps'"}
        items: list = []

    sp = _build_strategic_plan_summary(
        requirement={}, plan={}, review_result={}, pool=_Pool(),
        used_fallback=True, fallback_reason="KeyError: 'implementation_steps'",
    )
    assert sp["fallback"]["used_fallback"] is True
    assert sp["fallback"]["reason"] == "KeyError: 'implementation_steps'"
    assert "planner_bridge_failed" in sp["fallback"]["diagnostics"]


def test_strategic_plan_omits_fallback_block_on_normal_plan() -> None:
    from app.api.atlas_pipeline import _build_strategic_plan_summary

    class _Pool:
        root_goal = "g"
        warnings: list = []
        metadata: dict = {}
        items: list = []

    sp = _build_strategic_plan_summary(
        requirement={"interpreted_goal": "g"},
        plan={"implementation_steps": [{"title": "a"}]},
        review_result={}, pool=_Pool(),
    )
    assert "fallback" not in sp
