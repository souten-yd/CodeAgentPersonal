"""PIR-15 active rollout transition and legacy retirement gate tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.retirement_gate import (
    build_active_rollout_transition_evidence,
    build_pir15_retirement_gate,
    write_pir15_retirement_gate,
)
from tools import run_pir15_retirement_gate as cli


def _benchmark(*, passed: bool = True) -> dict:
    return {
        "source": "pir15_artifact_derived_normal_atlas_entrypoint_reports",
        "acceptance": {"status": "passed" if passed else "blocked", "blocked_reasons": [] if passed else ["x"]},
        "safety": {"manual_metrics_accepted": False},
    }


def _registry(*, legacy_count: int) -> dict:
    paths = [f"agent/legacy_consumer_{index}.py" for index in range(legacy_count)]
    return {
        "source": "python_ast_current_checkout_plus_runtime_telemetry",
        "entries": [
            {
                "name": "planning_context",
                "capability": "legacy_planner_context",
                "legacy_consumer_count": legacy_count,
                "legacy_consumer_paths": paths,
            },
            {
                "name": "generation_context",
                "capability": "legacy_planner_context",
                "legacy_consumer_count": legacy_count,
                "legacy_consumer_paths": paths,
            },
        ],
    }


def _rollout() -> dict:
    return {
        "source": "project_intelligence_public_facade_off_shadow_active_modes",
        "entries": [
            {"phase": "planning", "shadow_parity_status": "passed", "rollback_status": "passed"},
            {"phase": "generation", "shadow_parity_status": "passed", "rollback_status": "passed"},
        ],
    }


def _cutover() -> dict:
    return {
        "source": "project_intelligence_consumer_cutover_gate",
        "summary": {"gate_passed": True},
        "entries": [
            {"phase": "planning", "cutover_ready": True},
            {"phase": "generation", "cutover_ready": True},
        ],
    }


def _active_rollout() -> dict:
    return {
        "source": "pir15_isolated_production_rollout_preflight_transition",
        "status": "passed",
    }


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_active_rollout_transition_uses_concrete_modules_and_records_state(tmp_path: Path) -> None:
    evidence = build_active_rollout_transition_evidence(tmp_path / "ca_data")

    assert evidence["status"] == "passed"
    assert evidence["active_transition_recorded"] is True
    assert evidence["active_health"]["rollout"]["mode"] == "active"
    assert evidence["active_health"]["preflight"]["ok"] is True
    assert evidence["disabled_modules"] == {}
    assert evidence["safety"] == {
        "source_mutation": False,
        "legacy_retirement": False,
        "rollout_transition": True,
        "automatic_rollout": False,
    }


def test_retirement_gate_blocks_legacy_consumers_even_after_benchmark_and_cutover_pass() -> None:
    report = build_pir15_retirement_gate(
        benchmark_report=_benchmark(),
        consumer_registry=_registry(legacy_count=2),
        rollout_evidence=_rollout(),
        consumer_cutover_gate=_cutover(),
        active_rollout_evidence=_active_rollout(),
        data_migration_verified=True,
        docs_updated=True,
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert report["status"] == "blocked"
    assert report["summary"]["active_rollout_passed"] is True
    assert report["summary"]["legacy_consumer_count"] == 2
    assert report["summary"]["consumer_zero_capability_count"] == 0
    assert "legacy_capability_retirement_not_ready" in report["summary"]["blocked_reasons"]
    assert report["capabilities"][0]["blocked_reasons"] == ["legacy_consumers_remain"]
    assert report["safety"]["deletion_authorized"] is False


def test_retirement_gate_passes_only_when_all_live_gates_pass(tmp_path: Path) -> None:
    output = tmp_path / "retirement_gate.json"
    report = write_pir15_retirement_gate(
        output,
        benchmark_report_path=_write(tmp_path / "benchmark.json", _benchmark()),
        consumer_registry_path=_write(tmp_path / "registry.json", _registry(legacy_count=0)),
        rollout_evidence_path=_write(tmp_path / "rollout.json", _rollout()),
        consumer_cutover_gate_path=_write(tmp_path / "cutover.json", _cutover()),
        active_rollout_evidence_path=_write(tmp_path / "active.json", _active_rollout()),
        data_migration_verified=True,
        docs_updated=True,
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert report == json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["summary"]["blocked_reasons"] == []
    assert report["safety"]["legacy_retirement"] is True
    assert report["safety"]["deletion_authorized"] is True


def test_retirement_gate_cli_reports_blocked_without_passing(tmp_path: Path, monkeypatch) -> None:
    def fake_active(ca_data_dir: Path, output_path: Path) -> dict:
        assert ca_data_dir == tmp_path / "active-data"
        return _write(output_path, _active_rollout()) and _active_rollout()

    monkeypatch.setattr(cli, "write_active_rollout_transition_evidence", fake_active)

    exit_code = cli.main_cli(
        [
            "--benchmark-report",
            str(_write(tmp_path / "benchmark.json", _benchmark())),
            "--consumer-registry",
            str(_write(tmp_path / "registry.json", _registry(legacy_count=1))),
            "--rollout-evidence",
            str(_write(tmp_path / "rollout.json", _rollout())),
            "--consumer-cutover-gate",
            str(_write(tmp_path / "cutover.json", _cutover())),
            "--active-rollout-output",
            str(tmp_path / "active.json"),
            "--ca-data-dir",
            str(tmp_path / "active-data"),
            "--output-json",
            str(tmp_path / "retirement.json"),
            "--data-migration-verified",
            "--docs-updated",
            "--allow-blocked-exit-zero",
        ]
    )

    report = json.loads((tmp_path / "retirement.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["status"] == "blocked"
    assert report["summary"]["legacy_consumer_count"] == 1
