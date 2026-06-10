"""PIR-2 app lifecycle registration tests."""

from __future__ import annotations

from types import SimpleNamespace

from agent.project_intelligence.service_registry import (
    close_project_intelligence_service,
    get_project_intelligence_service,
    register_project_intelligence_service,
)
from agent.project_intelligence.rollout import ENV_ENABLED, RolloutConfig


def _app():
    return SimpleNamespace(state=SimpleNamespace())


def test_registry_constructs_once_and_closes(tmp_path) -> None:
    app = _app()
    rollout = RolloutConfig.from_env({ENV_ENABLED: "1"})
    first = register_project_intelligence_service(app, ca_data_dir=tmp_path, rollout=rollout)
    second = register_project_intelligence_service(app, ca_data_dir=tmp_path, rollout=rollout)
    assert first is second
    assert get_project_intelligence_service(app) is first
    assert app.state.project_intelligence is first.coordinator

    close_project_intelligence_service(app)
    assert get_project_intelligence_service(app) is None
    assert app.state.project_intelligence is None

