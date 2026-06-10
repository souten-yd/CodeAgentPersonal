"""PI-17 Planner production integration tests.

Acceptance criteria (implementation plan PI-17):
- off mode uses legacy context only;
- shadow mode does not change planner input;
- active mode includes manifest-backed context;
- stale/degraded readiness is explicit;
- planner does not access module stores directly.
"""

from __future__ import annotations

from agent.project_intelligence.adapters.atlas_planning import AtlasPlannerBridge
from agent.project_intelligence.contracts import PlanningContextRequest, ProjectIdentity
from agent.project_intelligence.factory import build_project_intelligence
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_SHADOW, RolloutConfig


def _identity():
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path="/tmp/p1")


def _request():
    return PlanningContextRequest(project=_identity(), objective="do x")


def _bridge(rollout):
    return AtlasPlannerBridge(build_project_intelligence(rollout=rollout))


LEGACY = {"files": ["a.py"], "source": "legacy"}


# --- Off mode uses legacy context only ---------------------------------------

def test_off_mode_uses_legacy_only() -> None:
    bridge = _bridge(RolloutConfig.off())
    res = bridge.build_planner_context(legacy_context=LEGACY, request=_request())
    assert res.mode == "off"
    assert res.used_intelligence is False
    assert res.context == LEGACY  # unchanged
    assert res.manifest_id is None


# --- Shadow mode does not change planner input -------------------------------

def test_shadow_mode_does_not_change_planner_input() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1", ENV_SHADOW: "1"}))
    res = bridge.build_planner_context(legacy_context=LEGACY, request=_request())
    assert res.mode == "shadow"
    assert res.used_intelligence is False
    assert res.context == LEGACY  # planner input unchanged
    # but a shadow artifact is produced for comparison.
    assert res.shadow_artifact is not None and "manifest_id" in res.shadow_artifact
    # and the coordinator recorded a shadow comparison telemetry record.
    assert bridge._coordinator.telemetry.comparison_artifacts()


# --- Active mode includes manifest-backed context ----------------------------

def test_active_mode_is_manifest_backed() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    res = bridge.build_planner_context(legacy_context=LEGACY, request=_request())
    assert res.mode == "active"
    assert res.used_intelligence is True
    assert res.context["source"] == "project_intelligence"
    assert res.manifest_id and res.context["manifest_id"] == res.manifest_id
    # legacy base preserved under the intelligence layer.
    assert res.context["files"] == ["a.py"]


# --- Stale/degraded readiness is explicit ------------------------------------

def test_readiness_is_explicit() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    res = bridge.build_planner_context(legacy_context=LEGACY, request=_request())
    # The disabled twin stub reports a non-ready readiness, surfaced explicitly as stale.
    assert res.readiness  # explicit string
    assert res.stale is True
    assert any("readiness" in d for d in res.diagnostics)


# --- Planner does not access module stores -----------------------------------

def test_bridge_exposes_no_store() -> None:
    bridge = _bridge(RolloutConfig.off())
    # The bridge holds only the coordinator; neither exposes a store/connection.
    for value in vars(bridge).values():
        name = type(value).__name__.lower()
        assert "store" not in name and "sqlite" not in name and "connection" not in name
    for value in vars(bridge._coordinator).values():
        name = type(value).__name__.lower()
        assert "store" not in name and "sqlite" not in name and "connection" not in name
