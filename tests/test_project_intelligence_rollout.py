"""PI-3 composition root and rollout model tests.

Acceptance criteria (implementation plan PI-3):
- off mode is behaviorally equivalent to baseline;
- shadow mode produces comparison artifacts only;
- no direct private-store calls from coordinator consumers;
- configuration parsing is deterministic and tested.
Plus: legacy Project Twin env vars map to compatibility configuration; injected deps;
phase-gated rollout (planning/generation/verification/repair/greenfield).
"""

from __future__ import annotations

from agent.project_intelligence.contracts import (
    GenerationContextRequest,
    PlanningContextRequest,
    ProjectIdentity,
    ProjectIntelligenceModule,
)
from agent.project_intelligence.coordinator import ProjectIntelligenceCoordinator
from agent.project_intelligence.factory import build_project_intelligence
from agent.project_intelligence.rollout import (
    ENV_ENABLED,
    ENV_PHASES,
    ENV_SHADOW,
    LEGACY_ENV_ENABLED,
    LEGACY_ENV_PHASES,
    PHASES,
    RolloutConfig,
)


def _identity() -> ProjectIdentity:
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path="/tmp/p1")


def _planning() -> PlanningContextRequest:
    return PlanningContextRequest(project=_identity(), objective="do x")


def _generation() -> GenerationContextRequest:
    return GenerationContextRequest(project=_identity(), plan_pool_id="pp", plan_item_id="pi")


# --- Deterministic config parsing --------------------------------------------

def test_config_parsing_is_deterministic_and_defaults_off() -> None:
    assert RolloutConfig.from_env({}) == RolloutConfig.from_env({})
    assert RolloutConfig.from_env({}).is_off()
    cfg = RolloutConfig.from_env({ENV_ENABLED: "true", ENV_PHASES: "generation, planning, bogus"})
    # Unknown phases dropped; result is a stable subset of PHASES.
    assert cfg.active_phases == frozenset({"planning", "generation"})
    assert cfg.enabled and not cfg.shadow
    assert cfg.mode() == "active"


def test_legacy_twin_env_maps_to_compatibility_config() -> None:
    cfg = RolloutConfig.from_env({LEGACY_ENV_ENABLED: "1", LEGACY_ENV_PHASES: "verification"})
    assert cfg.enabled is True
    assert cfg.active_phases == frozenset({"verification"})
    # New variables take precedence over legacy ones when both are present.
    cfg2 = RolloutConfig.from_env({ENV_ENABLED: "false", LEGACY_ENV_ENABLED: "true"})
    assert cfg2.enabled is False


def test_shadow_and_active_phase_gating() -> None:
    shadow = RolloutConfig.from_env({ENV_ENABLED: "1", ENV_SHADOW: "1"})
    assert shadow.mode() == "shadow"
    for phase in PHASES:
        assert shadow.shadow_active(phase) is True
        assert shadow.phase_active(phase) is False

    planning_only = RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "planning"})
    assert planning_only.phase_active("planning") is True
    assert planning_only.phase_active("generation") is False
    assert planning_only.mode_for_phase("planning") == "active"
    assert planning_only.mode_for_phase("generation") == "off"


# --- Off mode is behaviorally equivalent to baseline -------------------------

def test_off_mode_is_inert_baseline() -> None:
    coord = build_project_intelligence(rollout=RolloutConfig.off())
    pkg = coord.prepare_planning_context(_planning())
    assert pkg.context_manifest.rollout_mode == "off"
    assert pkg.project_state.readiness == "disabled"
    assert pkg.actual_twin_revision_id is None
    # Off mode records no telemetry (no shadow comparison, no augmentation).
    assert coord.telemetry.records() == []


def test_off_mode_generation_is_inert() -> None:
    coord = build_project_intelligence(rollout=RolloutConfig.off())
    pkg = coord.prepare_generation_context(_generation())
    assert pkg.context_manifest.rollout_mode == "off"
    assert pkg.target_files == []
    assert coord.telemetry.records() == []


# --- Shadow mode produces comparison artifacts only --------------------------

def test_shadow_mode_records_comparison_without_altering_inputs() -> None:
    coord = build_project_intelligence(
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_SHADOW: "1"})
    )
    baseline = build_project_intelligence(rollout=RolloutConfig.off()).prepare_planning_context(_planning())
    shadow_pkg = coord.prepare_planning_context(_planning())

    # The returned content matches baseline (inputs unchanged); only the manifest mode tag
    # and a telemetry artifact differ.
    assert shadow_pkg.project_state == baseline.project_state
    assert shadow_pkg.requirements == baseline.requirements
    assert shadow_pkg.impacted_areas == baseline.impacted_areas
    assert shadow_pkg.context_manifest.rollout_mode == "shadow"

    artifacts = coord.telemetry.comparison_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0].phase == "planning"
    assert artifacts[0].rollout_mode == "shadow"


# --- Active mode is wired and tagged -----------------------------------------

def test_active_mode_tags_manifest_active() -> None:
    coord = build_project_intelligence(rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}))
    pkg = coord.prepare_planning_context(_planning())
    assert pkg.context_manifest.rollout_mode == "active"
    assert coord.record_apply_result.__self__ is coord  # bound to coordinator
    # Active generation requests a refresh on apply (the real refresh lands in PI-4+).
    from agent.project_intelligence.contracts import ApplyResultRequest

    res = coord.record_apply_result(
        ApplyResultRequest(project=_identity(), plan_pool_id="pp", plan_item_id="pi", success=True)
    )
    assert res.refresh_requested is True
    assert res.accepted is False  # never an execution authority


# --- Protocol conformance + dependency injection -----------------------------

def test_coordinator_conforms_to_protocol_and_injects_deps() -> None:
    coord = build_project_intelligence(rollout=RolloutConfig.off())
    assert isinstance(coord, ProjectIntelligenceModule)
    assert isinstance(coord, ProjectIntelligenceCoordinator)


# --- No direct private-store reference in the coordinator --------------------

def test_coordinator_holds_no_store() -> None:
    coord = build_project_intelligence(rollout=RolloutConfig.off())
    for value in vars(coord).values():
        name = type(value).__name__.lower()
        assert "store" not in name and "connection" not in name and "sqlite" not in name
