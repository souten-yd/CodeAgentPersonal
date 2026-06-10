"""PIR-14 consumer registry and phase telemetry evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.consumer_registry import build_consumer_registry, write_consumer_registry
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_PHASES, ENV_SHADOW, RolloutConfig
from agent.project_intelligence.telemetry import TelemetryRecord


REPO_ROOT = Path(__file__).resolve().parents[1]


def _record(event_type: str, phase: str, **detail) -> TelemetryRecord:
    return TelemetryRecord(
        event_type=event_type,
        phase=phase,
        rollout_mode="shadow" if event_type == "shadow_comparison" else "active",
        project_id="p1",
        workspace_id="w1",
        detail=detail,
        recorded_at="2026-06-11T00:00:00+00:00",
    )


def test_registry_is_generated_from_current_source_and_runtime_telemetry(tmp_path: Path) -> None:
    records = [
        _record("shadow_comparison", "planning", parity=True),
        _record("phase_call", "planning"),
        _record("phase_call", "generation"),
        _record("rollback_drill", "generation", result="passed"),
    ]
    rollout = RolloutConfig.from_env(
        {ENV_ENABLED: "1", ENV_SHADOW: "1", ENV_PHASES: "planning,generation"}
    )

    registry = build_consumer_registry(
        REPO_ROOT,
        telemetry_records=records,
        rollout=rollout,
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert registry["source"] == "python_ast_current_checkout_plus_runtime_telemetry"
    assert registry["safety"] == {
        "mutation_authority": False,
        "automatic_rollout": False,
        "automatic_rollback": False,
        "legacy_retirement": False,
    }
    entries = {entry["name"]: entry for entry in registry["entries"]}
    assert entries["planning_context"]["current_mode"] == "shadow"
    assert entries["planning_context"]["call_count"] == 2
    assert entries["planning_context"]["shadow_parity_status"] == "parity_passed"
    assert entries["planning_context"]["legacy_consumer_count"] > 0
    assert entries["generation_context"]["current_mode"] == "shadow"
    assert entries["generation_context"]["rollback_status"] == "rollback_drill_passed"
    assert entries["verification_ingest"]["rollback_status"] == "flag_off_available_not_drilled"

    output = tmp_path / "registry.json"
    written = write_consumer_registry(
        REPO_ROOT,
        output,
        telemetry_records=records,
        rollout=rollout,
        generated_at="2026-06-11T00:00:00+00:00",
    )
    assert written == json.loads(output.read_text(encoding="utf-8"))


def test_registry_defaults_to_off_without_claiming_parity_or_cutover() -> None:
    registry = build_consumer_registry(
        REPO_ROOT,
        telemetry_records=[],
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert registry["rollout_mode"] == "off"
    assert registry["summary"]["telemetry_event_count"] == 0
    for entry in registry["entries"]:
        assert entry["current_mode"] == "off"
        assert entry["shadow_parity_status"] == "not_recorded"
        assert entry["rollback_status"] == "flag_off_available_not_drilled"
