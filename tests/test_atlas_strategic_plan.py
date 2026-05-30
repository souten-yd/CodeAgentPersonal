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
    assert steps[0]["target_files"] == ["index.html"]

    # GET returns it too (survives via pool.metadata)
    g = c.get(f"/api/atlas/plan-pools/{pid}").json()
    gsp = (g.get("metadata", {}) or {}).get("strategic_plan")
    assert isinstance(gsp, dict) and len(gsp.get("steps", [])) == 1


def test_strategic_plan_summary_bounds_and_shape():
    from app.api.atlas_pipeline import _build_strategic_plan_summary

    class _Item:
        title = "t"; description = "d"; goal = "g"; target_files = ["a.py"]; risk_level = "low"
        done_definition = ["dd"]; rollback_plan = ["rb"]; metadata = {"action_type": "update"}

    class _Pool:
        root_goal = "root goal"
        items = [_Item() for _ in range(50)]  # exceeds the 30 cap

    plan = {
        "user_goal": "do the thing",
        "selected_architecture": "arch",
        "implementation_steps": [
            {"title": f"s{i}", "description": "x" * 1000, "target_files": ["f.py"], "action_type": "create",
             "risk_level": "low", "verification": "v", "rollback": "r"}
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
    assert sp["selected_architecture"] == "arch"
    assert sp["review"]["overall_risk"] == "medium"
    assert sp["research"]["recommended_approach"] == "reuse X"
    assert sp["adversarial_critique"]["requires_revision"] is True
    assert sp["adversarial_critique"]["findings"][0]["angle"] == "security"
