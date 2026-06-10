"""PIR-14 operational evidence artifact tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.operational_evidence import build_operational_evidence, write_operational_evidence


def test_operational_evidence_records_current_platform_and_unavailable_rows(tmp_path: Path) -> None:
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "a.py").write_text("x = 1\n", encoding="utf-8")

    evidence = build_operational_evidence(
        tmp_path,
        platform_name="linux",
        generated_at="2026-06-11T00:00:00+00:00",
        file_budget=10,
    )

    assert evidence["current_platform"] == "linux"
    rows = {row["platform"]: row for row in evidence["platform_evidence"]}
    assert rows["linux"]["result"] == "observed"
    assert rows["windows"]["result"] == "unavailable"
    assert rows["docker"]["result"] == "unavailable"
    assert rows["runpod"]["result"] == "unavailable"
    assert evidence["summary"]["observed_platform_count"] == 1
    assert evidence["summary"]["unavailable_platform_count"] == 3
    assert evidence["scale_evidence"][0]["result"] == "passed"
    assert evidence["safety"] == {
        "platform_matrix_claimed": False,
        "large_repository_benchmark_claimed": False,
        "consumer_cutover": False,
        "source_mutation": False,
        "legacy_retirement": False,
    }

    output = tmp_path / "operational.json"
    written = write_operational_evidence(
        tmp_path,
        output,
        platform_name="linux",
        generated_at="2026-06-11T00:00:00+00:00",
        file_budget=10,
    )
    assert written == json.loads(output.read_text(encoding="utf-8"))


def test_operational_evidence_records_threshold_rollback(tmp_path: Path) -> None:
    evidence = build_operational_evidence(
        tmp_path,
        platform_name="linux",
        generated_at="2026-06-11T00:00:00+00:00",
        threshold_metrics={"latency_ms": 130.0},
    )

    rollback = evidence["threshold_rollback"]
    assert rollback["threshold_ok"] is False
    assert rollback["rolled_back"] is True
    assert rollback["start_stage"] == "generation"
    assert rollback["final_stage"] == "planning"
    assert rollback["failures"]


def test_operational_evidence_does_not_rollback_when_thresholds_pass(tmp_path: Path) -> None:
    evidence = build_operational_evidence(
        tmp_path,
        platform_name="linux",
        generated_at="2026-06-11T00:00:00+00:00",
        threshold_metrics={"latency_ms": 100.0},
    )

    rollback = evidence["threshold_rollback"]
    assert rollback["threshold_ok"] is True
    assert rollback["rolled_back"] is False
    assert rollback["final_stage"] == "generation"
