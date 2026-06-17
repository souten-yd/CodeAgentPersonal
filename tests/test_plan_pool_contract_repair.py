"""Tests for the templated plan-pool contract repair transform (pure source rewrite, no model)."""
from __future__ import annotations

import ast

from agent.twin_control_plane.plan_pool_contract_repair import repair_plan_pool_source
from agent.twin_control_plane.shared_cause_repair import assertion_preserving_edit


def test_rewrites_simple_call():
    old = "r = c.post('/api/atlas/plan-pools', json={'input': 'snapshot'}).json()\n"
    new, n = repair_plan_pool_source(old)
    assert n == 1
    assert "plan-pools?sync=1" in new
    assert "plan_payload" in new
    assert "'input': 'snapshot'" in new          # original body preserved
    ast.parse(new)                               # still valid python


def test_preserves_existing_kwargs():
    old = "c.post('/api/atlas/plan-pools', json={'input': goal, 'planner_mode': 'auto'})\n"
    new, n = repair_plan_pool_source(old)
    assert n == 1
    tree = ast.parse(new)
    # the json dict now has input, planner_mode AND plan_payload
    assert "planner_mode" in new and "plan_payload" in new
    assert "?sync=1" in new


def test_idempotent_when_already_sync():
    already = "c.post('/api/atlas/plan-pools?sync=1', json={'input': 'x', 'plan_payload': {}})\n"
    new, n = repair_plan_pool_source(already)
    assert n == 0
    assert new == already


def test_does_not_touch_unrelated_posts():
    src = "c.post('/api/atlas/other', json={'input': 'x'})\n"
    new, n = repair_plan_pool_source(src)
    assert n == 0 and new == src


def test_repair_is_assertion_preserving():
    old = (
        "def _create_pool(c):\n"
        "    return c.post('/api/atlas/plan-pools', json={'input': 'snapshot'}).json()\n"
        "def test_x(c):\n"
        "    pool = _create_pool(c)\n"
        "    assert pool['plan_pool']['items'][0]['item_id']\n"
    )
    new, n = repair_plan_pool_source(old)
    assert n == 1
    ok, removed = assertion_preserving_edit(old, new)
    assert ok is True and removed == []          # only the input helper changed, no assertion touched


def test_multiline_json_body():
    old = (
        "resp = client.post(\n"
        "    '/api/atlas/plan-pools',\n"
        "    json={\n"
        "        'input': 'build',\n"
        "        'planner_mode': 'auto',\n"
        "    },\n"
        ")\n"
    )
    new, n = repair_plan_pool_source(old)
    assert n == 1
    ast.parse(new)
    assert "?sync=1" in new and "plan_payload" in new
