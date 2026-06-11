"""PIR-15 artifact-derived benchmark runner tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.project_intelligence.live_benchmark import (
    build_artifact_comparative_report,
    derive_metrics_from_execution_report,
    load_benchmark_corpus,
    write_artifact_comparative_report,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "docs" / "generated" / "atlas_project_intelligence_pir15_benchmark_corpus.json"


def _task() -> object:
    corpus = load_benchmark_corpus(CORPUS)
    row = corpus["tasks"][0]
    return type(
        "Task",
        (),
        {
            "task_id": row["task_id"],
            "requirement": row["requirement"],
            "workspace_seed": row["workspace_seed"],
            "acceptance_text": row["acceptance_text"],
            "repetitions": row["repetitions"],
        },
    )()


def _report(*, status: str, accepted: bool, started: str = "2026-06-11T00:00:00+00:00") -> dict:
    return {
        "status": status,
        "started_at": started,
        "finished_at": "2026-06-11T00:00:01+00:00",
        "independent_acceptance": {"status": "passed" if accepted else "failed"},
        "restart_evidence": {"status": "passed" if accepted else "failed"},
        "steps": [{"name": "plan_pool"}, {"name": "proposal_approval"}],
        "artifacts": {"index.html": "Atlas Live Greenfield Ready" if accepted else ""},
        "metrics": {"verified_autonomous_completion": 999.0},
    }


def test_corpus_is_versioned_and_requires_identical_constraints() -> None:
    corpus = load_benchmark_corpus(CORPUS)

    assert corpus["corpus_version"] == "pir15-corpus-v1"
    assert corpus["constraints"]["model"] == "configured_atlas_model"
    assert corpus["tasks"][0]["task_id"] == "greenfield_single_html_ready"


def test_metrics_are_derived_from_execution_report_not_supplied_metrics() -> None:
    result = derive_metrics_from_execution_report(_task(), "final", _report(status="passed", accepted=True))

    assert result.metrics["verified_autonomous_completion"] == 1.0
    assert result.metrics["false_success"] == 0.0
    assert result.metrics["latency_ms"] == 1000.0
    assert result.metric_sources["verified_autonomous_completion"] == "execution_report_artifact"
    assert "caller_supplied_metrics_ignored" in result.warnings


def test_artifact_comparative_report_uses_corpus_task_coverage(tmp_path: Path) -> None:
    corpus = load_benchmark_corpus(CORPUS)
    task_id = corpus["tasks"][0]["task_id"]
    report = build_artifact_comparative_report(
        corpus,
        legacy_reports={task_id: _report(status="failed", accepted=False)},
        final_reports={task_id: _report(status="passed", accepted=True)},
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert report["source"] == "pir15_artifact_derived_normal_atlas_entrypoint_reports"
    assert report["safety"]["manual_metrics_accepted"] is False
    assert report["comparison"]["verdict"] == "improved"
    assert report["legacy"]["average_metrics"]["verified_autonomous_completion"] == 0.0
    assert report["final"]["average_metrics"]["verified_autonomous_completion"] == 1.0

    output = tmp_path / "benchmark.json"
    written = write_artifact_comparative_report(
        CORPUS,
        output,
        legacy_reports={task_id: _report(status="failed", accepted=False)},
        final_reports={task_id: _report(status="passed", accepted=True)},
        generated_at="2026-06-11T00:00:00+00:00",
    )
    assert written == json.loads(output.read_text(encoding="utf-8"))


def test_artifact_comparative_report_rejects_missing_task_reports() -> None:
    corpus = load_benchmark_corpus(CORPUS)
    task_id = corpus["tasks"][0]["task_id"]

    with pytest.raises(ValueError):
        build_artifact_comparative_report(
            corpus,
            legacy_reports={task_id: _report(status="failed", accepted=False)},
            final_reports={},
            generated_at="2026-06-11T00:00:00+00:00",
        )
