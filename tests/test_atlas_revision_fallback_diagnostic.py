"""Revision must not silently degrade to the rule-based fallback.

Previously `_do_pool_revision` swallowed any LLM-replan error with a bare `except: pass`
and also gave no signal when the LLM planner merely fell back, so a revision that did NOT
use the LLM planner looked identical to one that did. These tests pin the now-observable
diagnostics: `replan_result.revision_source` and `metadata.llm_revision_applied`.
"""
from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path, *, llm_json_fn=None):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = llm_json_fn
    return TestClient(main.app)


def _seed_pool(c):
    item = AtlasPlanItem(
        item_id="i1",
        pool_id="p1",
        title="Revision item",
        goal="do something",
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=["a.py"],
        metadata={"action_type": "update"},
    )
    pool = AtlasPlanPool(
        pool_id="p1",
        root_goal="do something",
        project_path=str(Path(c.app.state.atlas_ca_data_dir)),
        status="ready",
        items=[item],
    )
    storage = AtlasPlanPoolStorage(Path(c.app.state.atlas_ca_data_dir))
    journal = AtlasJournal(Path(c.app.state.atlas_ca_data_dir), workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    return pool.pool_id


def test_rule_based_fallback_is_surfaced_when_llm_planner_falls_back(tmp_path):
    # An llm_json_fn that returns None forces the planner bridge to fall back, so no LLM
    # replan is applied. The response must MAKE THAT VISIBLE instead of looking like a
    # successful LLM revision.
    c = _client(tmp_path, llm_json_fn=lambda _s, _u: None)
    pool_id = _seed_pool(c)
    resp = c.post(
        f"/api/atlas/plan-pools/{pool_id}/request-revision?sync=1",
        json={"note": "please also add a footer", "workspace_id": "default"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["replan_result"].get("revision_source") == "rule_based_fallback"
    assert body["plan_pool"]["metadata"].get("llm_revision_applied") is False


def test_llm_planner_error_is_captured_not_swallowed(tmp_path):
    # If the LLM revision path raises, the error must be captured into a diagnostic rather
    # than silently swallowed by `except: pass`.
    def _boom(_s, _u):
        raise RuntimeError("planner exploded")

    c = _client(tmp_path, llm_json_fn=_boom)
    pool_id = _seed_pool(c)
    resp = c.post(
        f"/api/atlas/plan-pools/{pool_id}/request-revision?sync=1",
        json={"note": "trigger the planner", "workspace_id": "default"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Either the bridge surfaced the error to our handler (llm_revision_error recorded) or it
    # internally fell back; in both cases the revision must be reported as rule-based, never as
    # a silent/ambiguous success.
    assert body["plan_pool"]["metadata"].get("llm_revision_applied") is False
    assert body["replan_result"].get("revision_source") == "rule_based_fallback"
