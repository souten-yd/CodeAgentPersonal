"""PIR-2 production composition root tests."""

from __future__ import annotations

from agent.project_intelligence.production_factory import build_production_project_intelligence
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_SHADOW, RolloutConfig


def test_off_mode_composes_disabled_modules_without_touching_legacy_behavior(tmp_path) -> None:
    service = build_production_project_intelligence(ca_data_dir=tmp_path, rollout=RolloutConfig.off())
    health = service.health()
    try:
        assert health["rollout"]["mode"] == "off"
        assert health["preflight"]["ok"] is True
        assert health["preflight"]["implementation_classes"]["digital_twin"] == "DisabledDigitalTwinModule"
    finally:
        service.close()


def test_shadow_mode_composes_concrete_durable_modules(tmp_path) -> None:
    service = build_production_project_intelligence(
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_SHADOW: "1"}),
    )
    health = service.health()
    try:
        classes = health["preflight"]["implementation_classes"]
        assert health["rollout"]["mode"] == "shadow"
        assert health["preflight"]["ok"] is True
        assert classes["digital_twin"] == "DigitalTwinModuleImpl"
        assert classes["blueprint"] == "ArchitectureBlueprintModuleImpl"
        assert classes["convergence"] == "ConvergenceModuleImpl"
        assert (tmp_path / "project_intelligence" / "rollout_state.json").is_file()
    finally:
        service.close()

