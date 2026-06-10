"""PIR-2 rollout preflight tests."""

from __future__ import annotations

import pytest

from agent.project_intelligence.production_factory import build_production_project_intelligence
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_PHASES, RolloutConfig


def test_active_mode_requires_concrete_healthy_modules(tmp_path) -> None:
    service = build_production_project_intelligence(
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "planning"}),
    )
    try:
        preflight = service.preflight()
        assert preflight["ok"] is True
        assert preflight["mode"] == "active"
        assert preflight["active_phases"] == ["planning"]
        assert preflight["disabled_modules"] == {}
    finally:
        service.close()


def test_unusable_store_path_blocks_active_promotion(tmp_path) -> None:
    bad_path = tmp_path / "project_intelligence" / "digital_twin.sqlite3"
    bad_path.mkdir(parents=True)
    with pytest.raises(Exception):
        build_production_project_intelligence(
            ca_data_dir=tmp_path,
            rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}),
        )

