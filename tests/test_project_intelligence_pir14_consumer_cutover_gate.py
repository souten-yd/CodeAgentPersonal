"""PIR-14 consumer cutover gate tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.consumer_cutover_gate import (
    build_consumer_cutover_gate,
    write_consumer_cutover_gate,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _lint(path: Path, *, passed: bool = True) -> Path:
    return _write_json(path, {"passed": passed, "summary": {"violation_count": 0 if passed else 1}})


def _rollout(path: Path) -> Path:
    return _write_json(
        path,
        {
            "entries": [
                {"phase": "planning", "shadow_parity_status": "passed", "rollback_status": "passed"},
                {"phase": "generation", "shadow_parity_status": "passed", "rollback_status": "passed"},
            ]
        },
    )


def _full_rollout(path: Path) -> Path:
    return _write_json(
        path,
        {
            "entries": [
                {"phase": "planning", "shadow_parity_status": "passed", "rollback_status": "passed"},
                {"phase": "generation", "shadow_parity_status": "passed", "rollback_status": "passed"},
                {"phase": "verification", "shadow_parity_status": "passed", "rollback_status": "passed"},
                {"phase": "recovery", "shadow_parity_status": "passed", "rollback_status": "passed"},
            ]
        },
    )


def test_cutover_gate_reports_connected_consumers_and_remaining_phase_blocks(tmp_path: Path) -> None:
    gate = build_consumer_cutover_gate(
        REPO_ROOT,
        legacy_lint_report_path=_lint(tmp_path / "lint.json"),
        rollout_evidence_path=_rollout(tmp_path / "rollout.json"),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert gate["summary"]["production_connected_count"] == 4
    assert gate["summary"]["cutover_ready_count"] == 2
    assert gate["summary"]["gate_passed"] is False
    assert gate["summary"]["legacy_dependency_lint_passed"] is True
    entries = {entry["name"]: entry for entry in gate["entries"]}
    assert entries["planning"]["cutover_ready"] is True
    assert entries["generation"]["cutover_ready"] is True
    assert entries["verification"]["cutover_ready"] is False
    assert entries["verification"]["blocked_reasons"] == [
        "shadow_parity_not_passed",
        "rollback_drill_not_passed",
    ]
    assert entries["recovery"]["cutover_ready"] is False
    assert gate["safety"] == {
        "advisory_only": True,
        "rollout_transition": False,
        "source_mutation": False,
        "legacy_retirement": False,
    }

    output = tmp_path / "cutover_gate.json"
    written = write_consumer_cutover_gate(
        REPO_ROOT,
        output,
        legacy_lint_report_path=_lint(tmp_path / "lint2.json"),
        rollout_evidence_path=_rollout(tmp_path / "rollout2.json"),
        generated_at="2026-06-11T00:00:00+00:00",
    )
    assert written == json.loads(output.read_text(encoding="utf-8"))


def test_cutover_gate_blocks_all_consumers_when_lint_fails(tmp_path: Path) -> None:
    gate = build_consumer_cutover_gate(
        REPO_ROOT,
        legacy_lint_report_path=_lint(tmp_path / "lint.json", passed=False),
        rollout_evidence_path=_rollout(tmp_path / "rollout.json"),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert gate["summary"]["legacy_dependency_lint_passed"] is False
    assert gate["summary"]["cutover_ready_count"] == 0
    for entry in gate["entries"]:
        assert "legacy_dependency_lint_not_passed" in entry["blocked_reasons"]


def test_cutover_gate_passes_when_all_phase_evidence_is_present(tmp_path: Path) -> None:
    gate = build_consumer_cutover_gate(
        REPO_ROOT,
        legacy_lint_report_path=_lint(tmp_path / "lint.json"),
        rollout_evidence_path=_full_rollout(tmp_path / "rollout.json"),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert gate["summary"]["production_connected_count"] == 4
    assert gate["summary"]["cutover_ready_count"] == 4
    assert gate["summary"]["gate_passed"] is True
    assert gate["summary"]["blocked_reasons"] == []
    assert all(entry["cutover_ready"] for entry in gate["entries"])
