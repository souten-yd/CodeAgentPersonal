"""PIR-14 shadow parity and rollback drill evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.project_intelligence.rollout_evidence import (
    build_rollout_evidence,
    write_rollout_evidence,
)


def test_rollout_evidence_records_shadow_parity_and_flag_rollback(tmp_path: Path) -> None:
    evidence = build_rollout_evidence(
        tmp_path,
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert evidence["source"] == "project_intelligence_public_facade_off_shadow_active_modes"
    assert evidence["summary"] == {
        "phase_count": 6,
        "shadow_parity_passed_count": 6,
        "rollback_passed_count": 6,
        "telemetry_event_count": 2,
    }
    assert evidence["safety"] == {
        "consumer_cutover": False,
        "source_mutation": False,
        "automatic_rollback": False,
        "legacy_retirement": False,
    }

    entries = {entry["phase"]: entry for entry in evidence["entries"]}
    assert entries["planning"]["baseline_mode"] == "off"
    assert entries["planning"]["shadow_mode"] == "shadow"
    assert entries["planning"]["active_mode_before_rollback"] == "active"
    assert entries["planning"]["mode_after_rollback"] == "off"
    assert entries["planning"]["mismatch_paths"] == []
    assert entries["generation"]["mismatch_paths"] == []
    assert entries["verification"]["baseline_mode"] == "off"
    assert entries["verification"]["shadow_mode"] == "shadow"
    assert entries["verification"]["mode_after_rollback"] == "off"
    assert entries["verification"]["mismatch_paths"] == []
    assert entries["recovery"]["shadow_parity_status"] == "passed"
    assert entries["recovery"]["rollback_status"] == "passed"
    assert entries["recovery"]["mode_after_rollback"] == "resume"
    assert entries["repair"]["shadow_mode"] == "shadow"
    assert entries["repair"]["mode_after_rollback"] == "off"
    assert entries["greenfield"]["shadow_mode"] == "shadow"
    assert entries["greenfield"]["mode_after_rollback"] == "off"

    output = tmp_path / "rollout_evidence.json"
    written = write_rollout_evidence(
        tmp_path,
        output,
        generated_at="2026-06-11T00:00:00+00:00",
    )
    assert written == json.loads(output.read_text(encoding="utf-8"))


def test_rollout_evidence_rejects_unsupported_phase(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported evidence phase"):
        build_rollout_evidence(tmp_path, phases=("benchmark",))
