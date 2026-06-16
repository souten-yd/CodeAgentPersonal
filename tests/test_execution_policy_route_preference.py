"""I2 — route_preferences pick the model's best route within the safe candidate set."""
from __future__ import annotations

from agent.model_forge.execution_policy import ExecutionPolicySelector, ModelCapabilityProfile
from agent.model_forge.route_matrix import ChangeClass, RouteMatrix, RouteSelector
from agent.model_forge.route_taxonomy import ForgeRoute


def _candidates(change=ChangeClass.MEDIUM):
    return RouteSelector(RouteMatrix()).select(change).candidates_considered


def test_preference_selects_best_safe_route():
    cands = _candidates(ChangeClass.MEDIUM)
    assert len(cands) >= 2
    # Prefer the LAST candidate strongly; it should be chosen over the default (first).
    prefs = {r: 0.1 for r in cands}
    prefs[cands[-1]] = 0.99
    pol = ExecutionPolicySelector().select(ChangeClass.MEDIUM, route_preferences=prefs)
    assert pol.route == cands[-1]
    assert any("benchmark_preferred_route" in r for r in pol.reasons)


def test_no_preferences_keeps_default_route():
    cands = _candidates(ChangeClass.MEDIUM)
    pol = ExecutionPolicySelector().select(ChangeClass.MEDIUM)
    assert pol.route == cands[0]  # RouteMatrix default unchanged
    assert not any("benchmark_preferred_route" in r for r in pol.reasons)


def test_preference_never_overrides_critical_gate():
    # A critical change must route through the critical gate regardless of preferences.
    prefs = {ForgeRoute.MICRO_PATCH: 0.99}
    pol = ExecutionPolicySelector().select(ChangeClass.CRITICAL, route_preferences=prefs)
    assert pol.route == ForgeRoute.CRITICAL_GATE


def test_preference_for_unsafe_route_is_ignored():
    # A preference for a route NOT in the safe candidates does not get selected.
    cands = _candidates(ChangeClass.MEDIUM)
    prefs = {ForgeRoute.DETERMINISTIC: 0.99}  # not a MEDIUM candidate
    pol = ExecutionPolicySelector().select(ChangeClass.MEDIUM, route_preferences=prefs)
    assert pol.route in cands
    assert pol.route != ForgeRoute.DETERMINISTIC
