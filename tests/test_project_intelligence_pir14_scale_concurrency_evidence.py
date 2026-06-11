"""PIR-14 scale and concurrency evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.scale_concurrency_evidence import (
    build_scale_concurrency_evidence,
    write_scale_concurrency_evidence,
)


def test_scale_concurrency_evidence_uses_measured_inventory_results(tmp_path: Path) -> None:
    evidence = build_scale_concurrency_evidence(
        file_count=25,
        concurrency=2,
        generated_at="2026-06-11T00:00:00+00:00",
    )

    data = evidence["evidence"]
    assert data["generated_file_count"] == 25
    assert data["concurrency"] == 2
    assert data["parse_error_count"] == 0
    assert data["concurrent_parse_error_count"] == 0
    assert data["result"] == "passed"
    assert data["inventory_duration_seconds"] >= 0
    assert data["concurrent_duration_seconds"] >= 0
    assert evidence["safety"] == {
        "temporary_workspace": True,
        "source_mutation": False,
        "rollout_transition": False,
        "legacy_retirement": False,
        "manual_metrics": False,
    }

    output = tmp_path / "scale.json"
    written = write_scale_concurrency_evidence(
        output,
        file_count=25,
        concurrency=2,
        generated_at="2026-06-11T00:00:00+00:00",
    )
    assert written == json.loads(output.read_text(encoding="utf-8"))
