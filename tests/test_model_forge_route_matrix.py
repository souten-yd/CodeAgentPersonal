"""PFG-18 — Route Matrix policy and selector tests.

Proves: large/critical changes cannot be forced through unsafe micro routes, critical
changes route through critical_gate, and route decisions are evidence-recorded.
"""
from __future__ import annotations

from agent.model_forge import (
    ChangeClass,
    RouteMatrix,
    RouteSelector,
    UNSAFE_MICRO_ROUTES,
)
from agent.model_forge.route_taxonomy import ForgeRoute


def _selector():
    return RouteSelector(RouteMatrix())


def test_micro_change_can_use_micro_route():
    sel = _selector().select(ChangeClass.MICRO, requested_route=ForgeRoute.MICRO_PATCH)
    assert sel.selected_route == ForgeRoute.MICRO_PATCH
    assert sel.overridden is False
    assert "requested_route_allowed" in sel.reasons


def test_large_change_cannot_be_forced_through_micro_route():
    sel = _selector().select(ChangeClass.LARGE, requested_route=ForgeRoute.MICRO_PATCH)
    assert sel.selected_route not in UNSAFE_MICRO_ROUTES
    assert sel.overridden is True
    assert any("unsafe_micro_route_blocked" in r for r in sel.reasons)
    # The matrix never lists an unsafe micro route as a candidate for LARGE.
    assert not (set(sel.candidates_considered) & UNSAFE_MICRO_ROUTES)


def test_critical_change_forces_critical_gate():
    sel = _selector().select(ChangeClass.CRITICAL, requested_route=ForgeRoute.DIRECT_PATCH)
    assert sel.selected_route == ForgeRoute.CRITICAL_GATE
    assert sel.critical_gate_required is True
    assert sel.overridden is True
    assert any("critical_change_forces_critical_gate" in r for r in sel.reasons)


def test_critical_without_request_still_uses_gate():
    sel = _selector().select(ChangeClass.CRITICAL)
    assert sel.selected_route == ForgeRoute.CRITICAL_GATE
    assert any("critical_change_routes_through_critical_gate" in r for r in sel.reasons)


def test_default_route_when_none_requested():
    sel = _selector().select(ChangeClass.SMALL)
    assert sel.selected_route == ForgeRoute.DIRECT_PATCH  # first SMALL candidate
    assert any("default_route_for_small" in r for r in sel.reasons)
    assert sel.decided_at  # decision recorded


def test_repair_task_pulls_in_repair_routes():
    sel = _selector().select(ChangeClass.MEDIUM, task_category="repair")
    assert ForgeRoute.PORTAL_REPLAY_REPAIR in sel.candidates_considered
    assert ForgeRoute.REPAIR_LOOP in sel.candidates_considered
    assert sel.selected_route == ForgeRoute.REPAIR_LOOP


def test_greenfield_uses_skeleton_route():
    sel = _selector().select(ChangeClass.GREENFIELD)
    assert sel.selected_route == ForgeRoute.GREENFIELD_SKELETON
