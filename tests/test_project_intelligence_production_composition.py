"""PIR-2 production composition root tests."""

from __future__ import annotations

from agent.project_intelligence.contracts import PlanningContextRequest, ProjectIdentity, ProjectMode
from agent.project_intelligence.production_factory import build_production_project_intelligence
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_PHASES, ENV_SHADOW, RolloutConfig


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


def test_active_planning_returns_concrete_twin_context(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def message():\n    return 'ready'\n", encoding="utf-8")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text(
        "from app import message\n\n\ndef test_message():\n    assert message() == 'ready'\n",
        encoding="utf-8",
    )
    service = build_production_project_intelligence(
        ca_data_dir=tmp_path / "data",
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1", ENV_PHASES: "planning"}),
    )
    try:
        package = service.coordinator.prepare_planning_context(
            PlanningContextRequest(
                project=ProjectIdentity(
                    project_id="pir15-existing",
                    workspace_id="existing-workspace",
                    project_path=str(repo),
                ),
                objective="Update the existing project safely.",
                target_refs=["file://app.py"],
                correlation_id="active-planning-test",
            )
        )
        assert package.project_state.readiness == "ready"
        assert package.project_state.twin_revision_id
        assert package.actual_twin_revision_id == package.project_state.twin_revision_id
        assert package.context_manifest.actual_twin_revision_id == package.actual_twin_revision_id
        assert package.project_mode == ProjectMode.EXISTING
        assert "context" in package.project_state.available_capabilities
    finally:
        service.close()

