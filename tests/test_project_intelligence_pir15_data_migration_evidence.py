"""PIR-15 data-migration evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.data_migration_evidence import (
    build_pir15_data_migration_evidence,
    write_pir15_data_migration_evidence,
)


def _benchmark(*, passed: bool = True) -> dict:
    return {
        "source": "pir15_artifact_derived_normal_atlas_entrypoint_reports",
        "acceptance": {"status": "passed" if passed else "blocked"},
        "safety": {"manual_metrics_accepted": False},
    }


def _registry(*, legacy_count: int = 0) -> dict:
    paths = [f"agent/legacy_consumer_{index}.py" for index in range(legacy_count)]
    return {
        "source": "python_ast_current_checkout_plus_runtime_telemetry",
        "entries": [
            {
                "name": "planning_context",
                "capability": "legacy_planner_context",
                "legacy_consumer_count": legacy_count,
                "legacy_consumer_paths": paths,
                "facade_entrypoint": "ProjectIntelligenceModule.prepare_planning_context",
                "owner": "agent/project_intelligence/adapters/atlas_planning.py",
            },
            {
                "name": "verification_ingest",
                "capability": "legacy_verification_gate",
                "legacy_consumer_count": 0,
                "legacy_consumer_paths": [],
                "facade_entrypoint": "ProjectIntelligenceModule.record_verification_result",
                "owner": "agent/project_intelligence/adapters/atlas_verification.py",
            },
        ],
        "summary": {"legacy_consumer_count": legacy_count},
        "parse_errors": [],
    }


def _rollout() -> dict:
    phases = ["planning", "generation", "verification", "recovery", "repair", "greenfield"]
    return {
        "source": "project_intelligence_public_facade_off_shadow_active_modes",
        "entries": [
            {"phase": phase, "shadow_parity_status": "passed", "rollback_status": "passed"}
            for phase in phases
        ],
        "summary": {
            "phase_count": len(phases),
            "shadow_parity_passed_count": len(phases),
            "rollback_passed_count": len(phases),
        },
        "safety": {
            "source_mutation": False,
            "legacy_retirement": False,
            "consumer_cutover": False,
        },
    }


def _cutover() -> dict:
    return {
        "source": "project_intelligence_consumer_cutover_gate",
        "summary": {"gate_passed": True},
        "safety": {"source_mutation": False, "legacy_retirement": False},
    }


def _active_rollout() -> dict:
    return {
        "source": "pir15_isolated_production_rollout_preflight_transition",
        "status": "passed",
        "safety": {"source_mutation": False, "legacy_retirement": False},
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _paths(tmp_path: Path, *, legacy_count: int = 0) -> dict[str, Path]:
    return {
        "benchmark_report_path": _write(tmp_path / "benchmark.json", _benchmark()),
        "consumer_registry_path": _write(tmp_path / "registry.json", _registry(legacy_count=legacy_count)),
        "rollout_evidence_path": _write(tmp_path / "rollout.json", _rollout()),
        "consumer_cutover_gate_path": _write(tmp_path / "cutover.json", _cutover()),
        "active_rollout_evidence_path": _write(tmp_path / "active.json", _active_rollout()),
    }


def test_data_migration_evidence_passes_with_current_artifact_gates(tmp_path: Path) -> None:
    evidence = build_pir15_data_migration_evidence(
        **_paths(tmp_path),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert evidence["status"] == "passed"
    assert evidence["summary"]["data_migration_verified"] is True
    assert evidence["summary"]["consumer_registry_legacy_count"] == 0
    assert evidence["summary"]["consumer_zero_capability_count"] == 2
    assert evidence["summary"]["blocked_reasons"] == []
    assert evidence["safety"] == {
        "source_mutation": False,
        "legacy_retirement": False,
        "deletion_authorized": False,
        "manual_flag_accepted": False,
        "unavailable_counts_as_passed": False,
    }


def test_data_migration_evidence_blocks_legacy_consumers(tmp_path: Path) -> None:
    evidence = build_pir15_data_migration_evidence(
        **_paths(tmp_path, legacy_count=1),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert evidence["status"] == "blocked"
    assert "consumer_registry_legacy_consumers_remain" in evidence["summary"]["blocked_reasons"]
    assert "capability_migration_not_verified" in evidence["summary"]["blocked_reasons"]
    failed = [entry for entry in evidence["capabilities"] if not entry["migration_verified"]]
    assert failed[0]["blocked_reasons"] == ["legacy_consumers_remain"]


def test_data_migration_evidence_blocks_missing_artifact(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths["consumer_cutover_gate_path"] = tmp_path / "missing-cutover.json"

    evidence = build_pir15_data_migration_evidence(
        **paths,
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert evidence["status"] == "blocked"
    assert "required_artifact_unavailable" in evidence["summary"]["blocked_reasons"]
    assert "consumer_cutover_gate_not_passed" in evidence["summary"]["blocked_reasons"]
    assert any(check["name"] == "missing-cutover.json" and not check["exists"] for check in evidence["artifact_checks"])


def test_write_data_migration_evidence_round_trips_json(tmp_path: Path) -> None:
    output = tmp_path / "migration.json"
    evidence = write_pir15_data_migration_evidence(
        output,
        **_paths(tmp_path),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert evidence == json.loads(output.read_text(encoding="utf-8"))
    assert evidence["status"] == "passed"
