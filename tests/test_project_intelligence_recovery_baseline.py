"""PIR-0 recovery baseline, executable inventory, and regression locks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.project_intelligence.inspection.consumer_inventory import build_inventory

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_INVENTORY = REPO_ROOT / "docs" / "generated" / "atlas_project_intelligence_consumer_inventory.json"


def _inventory() -> dict:
    return build_inventory(REPO_ROOT)


def test_consumer_inventory_generator_finds_current_production_surface() -> None:
    inv = _inventory()
    assert inv["source"] == "python_ast_current_checkout"
    assert inv["summary"]["production_entrypoint_count"] >= 2
    assert inv["summary"]["facade_module_count"] >= 4
    assert inv["summary"]["adapter_module_count"] == 6
    assert inv["summary"]["legacy_production_consumer_count"] > 0
    assert not inv["parse_errors"]


def test_generated_inventory_artifact_matches_current_schema() -> None:
    assert GENERATED_INVENTORY.is_file()
    artifact = json.loads(GENERATED_INVENTORY.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == 1
    assert artifact["source"] == "python_ast_current_checkout"
    assert artifact["summary"]["critical_finding_count"] >= 6
    assert {row["issue_code"] for row in artifact["critical_findings"]} >= {
        "PIR0-C01",
        "PIR0-C02",
        "PIR0-C03",
        "PIR0-C04",
        "PIR0-C05",
        "PIR0-C06",
    }


def test_inventory_records_exact_facade_call_counts() -> None:
    inv = _inventory()
    assert any(
        row["legacy_module"] == "agent.atlas_repo_context_service"
        and row["production_consumer_count"] == 0
        and row["adapter_consumer_count"] >= 1
        and row["legacy_internal_consumer_count"] >= 1
        for row in inv["legacy_consumers"]
    )
    assert any(
        row["legacy_module"] == "agent.atlas_verification_gate_service"
        for row in inv["legacy_consumers"]
    )
    assert inv["summary"]["concrete_facade_count"] == len(inv["module_implementations"]["concrete_modules"])


def test_recovery_status_selects_next_active_package() -> None:
    status = (REPO_ROOT / "docs" / "atlas_project_intelligence_recovery_current_status.md").read_text(
        encoding="utf-8"
    )
    assert "Current package: `PIR-15`" in status
    assert "| PIR-0 | baseline, inventory, regression locks | acceptance_complete |" in status
    assert "| PIR-1 | durable concrete modules | acceptance_complete |" in status
    assert "| PIR-2 | production composition and rollout preflight | acceptance_complete |" in status
    assert "| PIR-3 | source snapshots and Twin refresh | acceptance_complete |" in status
    assert "| PIR-4 | durable event and delivery integration | acceptance_complete |" in status
    assert "| PIR-5 | verification ingest, context, impact, test selection | acceptance_complete |" in status
    assert "| PIR-6 | whole-project semantic graph | acceptance_complete |" in status
    assert "| PIR-7 | CFG, data flow, state/event/resource graphs | acceptance_complete |" in status
    assert "| PIR-8 | durable Blueprint planning and review | acceptance_complete |" in status
    assert "| PIR-9 | Convergence correctness and evidence policy | acceptance_complete |" in status
    assert "| PIR-10 | Planner and PlanPool production integration | acceptance_complete |" in status
    assert "| PIR-11 | Proposal, Safe Apply, and refresh integration | acceptance_complete |" in status
    assert "| PIR-12 | Verification, recovery, checkpoint, resume | acceptance_complete |" in status
    assert "| PIR-13 | real Greenfield E2E | acceptance_complete |" in status
    assert "| PIR-14 | CI, platform, scale, and consumer cutover | acceptance_complete |" in status
    assert "| PIR-15 | real benchmark and retirement | in_progress |" in status


def test_legacy_status_treats_pi_as_foundation_not_completion() -> None:
    status = (REPO_ROOT / "docs" / "atlas_project_intelligence_current_status.md").read_text(encoding="utf-8")
    assert "Foundation Track" in status
    assert "IMPLEMENTATION COMPLETE (PI-0..PI-25)" not in status.split("## Program status", 1)[1].split(
        "## Important interpretation", 1
    )[0]


def test_pir0_c01_production_factory_no_longer_constructs_disabled_modules(tmp_path: Path) -> None:
    from agent.project_intelligence.production_factory import build_production_project_intelligence
    from agent.project_intelligence.rollout import ENV_ENABLED, RolloutConfig

    service = build_production_project_intelligence(
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}),
    )
    try:
        classes = service.preflight()["implementation_classes"]
        assert not any(name.startswith("Disabled") for name in classes.values())
    finally:
        service.close()


@pytest.mark.xfail(strict=True, reason="PIR0-C02: active coordinator still returns baseline package output")
def test_pir0_c02_active_coordinator_returns_real_module_output() -> None:
    from agent.project_intelligence.contracts import PlanningContextRequest, ProjectIdentity
    from agent.project_intelligence.factory import build_project_intelligence
    from agent.project_intelligence.rollout import ENV_ENABLED, RolloutConfig

    coord = build_project_intelligence(rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}))
    pkg = coord.prepare_planning_context(
        PlanningContextRequest(
            project=ProjectIdentity(project_id="p", workspace_id="w", project_path="/tmp/p"),
            objective="baseline lock",
        )
    )
    assert pkg.project_state.readiness == "ready"
    assert pkg.actual_twin_revision_id is not None
    assert pkg.context_manifest.included_refs


@pytest.mark.xfail(strict=True, reason="PIR0-C03: real Atlas APIs still import legacy consumers")
def test_pir0_c03_atlas_api_uses_project_intelligence_adapters() -> None:
    inv = _inventory()
    legacy_api_imports = [
        entry for entry in inv["production_entrypoints"] if entry["imports_legacy_capability"]
    ]
    assert legacy_api_imports == []


def test_pir0_c04_c05_concrete_twin_and_convergence_facades_exist() -> None:
    inv = _inventory()
    concrete = {row["class_name"] for row in inv["module_implementations"]["concrete_modules"]}
    assert {"DigitalTwinModuleImpl", "ConvergenceModuleImpl"} <= concrete


def test_pir0_c06_no_memory_database_defaults_remain() -> None:
    inv = _inventory()
    memory_defaults = [row for row in inv["database_defaults"] if row["memory_default_count"]]
    assert memory_defaults == []


def test_pir0_c07_plan_compiler_rejects_dependency_cycles() -> None:
    from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
    from agent.architecture_blueprint.lifecycle import planner_decision
    from agent.project_intelligence.plan_compiler import compile_plan

    revision = BlueprintRevision(
        blueprint_id="bp",
        revision_id="rev",
        project_id="p",
        scope="full_project",
        source_requirement_ids=["R1"],
        selected_architecture=planner_decision("d", "target", [], "", []),
        elements=[
            BlueprintElement(
                element_id="a",
                canonical_ref="bp://a",
                element_type="file",
                name="a.py",
                requirement_ids=["R1"],
                depends_on_element_ids=["b"],
                expected_actual_refs=["file://a.py"],
            ),
            BlueprintElement(
                element_id="b",
                canonical_ref="bp://b",
                element_type="file",
                name="b.py",
                requirement_ids=["R1"],
                depends_on_element_ids=["a"],
                expected_actual_refs=["file://b.py"],
            ),
        ],
    )
    with pytest.raises(ValueError):
        compile_plan(revision, project_mode="empty")

