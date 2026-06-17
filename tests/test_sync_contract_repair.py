"""Tests for the generic, endpoint-parameterized sync-contract repair transform."""
from __future__ import annotations

import ast

from agent.twin_control_plane.shared_cause_repair import assertion_preserving_edit
from agent.twin_control_plane.sync_contract_repair import repair_sync_contracts


def test_adds_sync_to_multiple_endpoints():
    src = (
        "c.post('/api/atlas/plan-pools', json={'input': 'x'})\n"
        "c.post('/api/atlas/verification/run', json={'pool_id': p, 'item_id': i})\n"
    )
    new, n = repair_sync_contracts(src)
    assert n == 2
    assert "plan-pools?sync=1" in new and "verification/run?sync=1" in new
    assert "plan_payload" in new                  # plan-pools gets a payload
    assert new.count("plan_payload") == 1         # verification/run does NOT
    ast.parse(new)


def test_does_not_rewrite_url_inside_an_assertion():
    # the exact over-reach a naive global regex hits: a route-existence assertion must stay untouched.
    src = (
        "def test_routes(app):\n"
        "    routes = {r.path for r in app.routes}\n"
        "    assert '/api/atlas/verification/run' in routes\n"
    )
    new, n = repair_sync_contracts(src)
    assert n == 0
    assert new == src                             # nothing rewritten -> assertion intact
    ok, _ = assertion_preserving_edit(src, new)
    assert ok is True


def test_only_configured_endpoints_match():
    src = "c.post('/api/atlas/other-thing', json={'x': 1})\n"
    new, n = repair_sync_contracts(src)
    assert n == 0 and new == src


def test_idempotent_when_already_sync():
    src = "c.post('/api/atlas/verification/run?sync=1', json={'x': 1})\n"
    new, n = repair_sync_contracts(src)
    assert n == 0 and new == src


def test_custom_endpoint_map():
    src = "c.post('/api/custom/thing', json={'a': 1})\n"
    new, n = repair_sync_contracts(src, endpoints={"/api/custom/thing": None})
    assert n == 1 and "thing?sync=1" in new and "plan_payload" not in new
