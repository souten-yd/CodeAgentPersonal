"""PI-18 Generator and repair production integration tests.

Acceptance criteria (implementation plan PI-18):
- stale Actual revision blocks or refreshes before generation;
- missing imaginary symbols are not presented as real;
- multi-file names and contracts remain coherent;
- Proposal stores context manifest;
- repair uses actual failure evidence and bounded decisions.
"""

from __future__ import annotations

from agent.project_intelligence.adapters.atlas_generation import AtlasGeneratorBridge
from agent.project_intelligence.contracts import (
    GenerationContextRequest,
    ProjectIdentity,
    RuntimeObservationRecord,
)
from agent.project_intelligence.factory import build_project_intelligence
from agent.project_intelligence.rollout import ENV_ENABLED, RolloutConfig


def _identity():
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path="/tmp/p1")


def _request():
    return GenerationContextRequest(project=_identity(), plan_pool_id="pp", plan_item_id="pi")


def _bridge(rollout):
    return AtlasGeneratorBridge(build_project_intelligence(rollout=rollout))


LEGACY = {"target": "svc.py", "source": "legacy"}


# --- Stale Actual revision blocks / refreshes --------------------------------

def test_stale_actual_revision_blocks_and_requests_refresh() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    res = bridge.build_generation_context(
        request=_request(), legacy_context=LEGACY,
        base_revision="rev-A", current_actual_revision="rev-B",  # moved under us
    )
    assert res.blocked is True and res.refresh_requested is True
    assert any("stale actual revision" in d for d in res.diagnostics)


def test_matching_revision_proceeds() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    res = bridge.build_generation_context(
        request=_request(), legacy_context=LEGACY,
        base_revision="rev-A", current_actual_revision="rev-A",
    )
    assert res.blocked is False and res.used_intelligence is True


# --- Off / shadow behaviour --------------------------------------------------

def test_off_mode_legacy_only() -> None:
    bridge = _bridge(RolloutConfig.off())
    res = bridge.build_generation_context(request=_request(), legacy_context=LEGACY,
                                          base_revision="r", current_actual_revision="r")
    assert res.mode == "off" and res.context == LEGACY and res.manifest_id is None


# --- Planned vs real symbols -------------------------------------------------

def test_planned_symbols_not_presented_as_real() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    res = bridge.build_generation_context(request=_request(), legacy_context=LEGACY,
                                          base_revision="r", current_actual_revision="r")
    # actual_symbols carries only real twin symbols (empty in the disabled stub),
    # blueprint_contracts are explicitly flagged planned -> never confused with real.
    assert isinstance(res.context["actual_symbols"], list)
    assert all(c.get("planned") is True for c in res.context["blueprint_contracts"])
    assert "prohibited_divergences" in res.context and "preserve_behaviors" in res.context


# --- Proposal stores context manifest ----------------------------------------

def test_proposal_stores_context_manifest() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    res = bridge.build_generation_context(request=_request(), legacy_context=LEGACY,
                                          base_revision="r5", current_actual_revision="r5")
    md = res.proposal_metadata()
    assert md["context_manifest_id"] == res.manifest_id and md["context_manifest_id"]
    assert md["base_revision"] == "r5"


# --- Repair uses actual failure evidence + bounded decision ------------------

def test_repair_uses_failure_evidence_and_bounded_action() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    obs = [
        RuntimeObservationRecord(observation_id="o1", project_id="p1", workspace_id="w1",
                                 result="failed", summary="test failed"),
        RuntimeObservationRecord(observation_id="o2", project_id="p1", workspace_id="w1",
                                 result="passed", summary="ok"),
    ]
    res = bridge.build_repair_context(failure_observations=obs, decision_action="repair_current_item",
                                      affected_items=["pi"])
    assert res.bounded is True and res.action == "repair_current_item"
    assert res.failure_evidence_refs == ["o1"]  # only failed evidence


def test_repair_rejects_non_bounded_action() -> None:
    bridge = _bridge(RolloutConfig.from_env({ENV_ENABLED: "1"}))
    obs = [RuntimeObservationRecord(observation_id="o1", project_id="p1", workspace_id="w1",
                                    result="failed", summary="x")]
    res = bridge.build_repair_context(failure_observations=obs, decision_action="auto_apply_and_merge")
    assert res.bounded is False and res.action == "halt_unsafe"
