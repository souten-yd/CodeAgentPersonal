"""PIR-15 artifact-derived comparative benchmark runner.

The runner accepts Atlas execution reports from normal entrypoints and derives metrics from
those artifacts. It does not accept caller-supplied benchmark metrics as results.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from agent.project_intelligence.benchmark import BenchmarkArm, BenchmarkConstraints, run_comparative


@dataclass(frozen=True)
class BenchmarkCorpusTask:
    task_id: str
    requirement: str
    workspace_seed: str
    acceptance_text: str
    repetitions: int


@dataclass(frozen=True)
class ArtifactMetricResult:
    task_id: str
    repetition: int
    arm: str
    status: str
    metrics: dict[str, float]
    metric_sources: dict[str, str]
    warnings: list[str]


def load_benchmark_corpus(path: str | Path) -> dict[str, Any]:
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    if corpus.get("schema_version") != 1:
        raise ValueError("unsupported PIR-15 benchmark corpus schema")
    if not corpus.get("corpus_version"):
        raise ValueError("PIR-15 benchmark corpus must be versioned")
    if not corpus.get("tasks"):
        raise ValueError("PIR-15 benchmark corpus must contain tasks")
    return corpus


def _constraints(raw: dict[str, Any]) -> BenchmarkConstraints:
    return BenchmarkConstraints(
        model=str(raw["model"]),
        repository=str(raw["repository"]),
        requirement=str(raw["requirement"]),
        token_budget=int(raw["token_budget"]),
        tool_authority=str(raw["tool_authority"]),
        retry_limit=int(raw["retry_limit"]),
    )


def _elapsed_ms(report: dict[str, Any]) -> float:
    started = str(report.get("started_at") or "")
    finished = str(report.get("finished_at") or "")
    if not started or not finished:
        return 0.0
    try:
        start = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, (end - start).total_seconds() * 1000.0)


def derive_metrics_from_execution_report(
    task: BenchmarkCorpusTask,
    arm: str,
    report: dict[str, Any],
    *,
    repetition: int = 1,
) -> ArtifactMetricResult:
    warnings: list[str] = []
    if "metrics" in report:
        warnings.append("caller_supplied_metrics_ignored")

    status = str(report.get("status") or "unknown")
    independent = report.get("independent_acceptance") or {}
    independent_status = str(independent.get("status") or report.get("acceptance_status") or "")
    accepted = independent_status == "passed"
    if not independent_status and status == "passed":
        accepted = task.acceptance_text in json.dumps(report.get("artifacts", {}), ensure_ascii=False)

    restart = report.get("restart_evidence") or {}
    errors = report.get("errors") or []
    warnings_from_report = report.get("warnings") or []
    interventions = [
        step
        for step in report.get("steps", [])
        if str(step.get("name") or "").lower() in {"proposal_approval", "planitem_approval", "human_approval"}
    ]
    verified = status == "passed" and accepted and not errors
    false_success = status == "passed" and not accepted

    metrics = {
        "verified_autonomous_completion": 1.0 if verified else 0.0,
        "false_success": 1.0 if false_success else 0.0,
        "autonomous_recovery": 1.0 if (restart.get("status") == "passed") else 0.0,
        "regression_escape": 0.0 if not errors else 1.0,
        "requirement_coverage": 1.0 if accepted else 0.0,
        "human_intervention": float(len(interventions)),
        "latency_ms": _elapsed_ms(report),
        "resume_fidelity": 1.0 if (restart.get("status") == "passed") else 0.0,
    }
    sources = {metric: "execution_report_artifact" for metric in metrics}
    if warnings_from_report:
        warnings.append(f"execution_report_warnings={len(warnings_from_report)}")
    return ArtifactMetricResult(
        task_id=task.task_id,
        repetition=repetition,
        arm=arm,
        status=status,
        metrics=metrics,
        metric_sources=sources,
        warnings=warnings,
    )


def _average_metrics(results: list[ArtifactMetricResult]) -> dict[str, float]:
    metrics = sorted({metric for result in results for metric in result.metrics})
    return {metric: mean(result.metrics[metric] for result in results if metric in result.metrics) for metric in metrics}


def _reports_for_task(raw_reports: dict[str, Any], task: BenchmarkCorpusTask, arm: str) -> list[dict[str, Any]]:
    if task.task_id not in raw_reports:
        raise ValueError(f"{arm} reports missing task {task.task_id}")
    raw = raw_reports[task.task_id]
    reports = list(raw) if isinstance(raw, list) else [raw]
    if len(reports) != task.repetitions:
        raise ValueError(f"{arm} reports for {task.task_id} must contain {task.repetitions} repetitions")
    if not all(isinstance(report, dict) for report in reports):
        raise ValueError(f"{arm} reports for {task.task_id} must be execution report objects")
    return reports


_NON_BLOCKING_ACCEPTANCE_REGRESSIONS = {"latency_ms"}


def _blocking_acceptance_regressions(regressed_metrics: list[str]) -> list[str]:
    return [
        metric for metric in regressed_metrics
        if metric not in _NON_BLOCKING_ACCEPTANCE_REGRESSIONS
    ]


def build_artifact_comparative_report(
    corpus: dict[str, Any],
    *,
    legacy_reports: dict[str, dict[str, Any]],
    final_reports: dict[str, dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    tasks = [
        BenchmarkCorpusTask(
            task_id=str(row["task_id"]),
            requirement=str(row["requirement"]),
            workspace_seed=str(row["workspace_seed"]),
            acceptance_text=str(row["acceptance_text"]),
            repetitions=int(row.get("repetitions", 1)),
        )
        for row in corpus["tasks"]
    ]
    task_ids = {task.task_id for task in tasks}
    if set(legacy_reports) != task_ids or set(final_reports) != task_ids:
        raise ValueError("legacy and final reports must cover exactly the versioned corpus tasks")

    constraints = _constraints(corpus["constraints"])
    legacy_results = []
    final_results = []
    for task in tasks:
        legacy_results.extend(
            derive_metrics_from_execution_report(task, "legacy", report, repetition=index)
            for index, report in enumerate(_reports_for_task(legacy_reports, task, "legacy"), start=1)
        )
        final_results.extend(
            derive_metrics_from_execution_report(task, "final", report, repetition=index)
            for index, report in enumerate(_reports_for_task(final_reports, task, "final"), start=1)
        )
    legacy_arm = BenchmarkArm("legacy", constraints, _average_metrics(legacy_results))
    final_arm = BenchmarkArm("final", constraints, _average_metrics(final_results))
    comparison = run_comparative(legacy_arm, final_arm)
    blocked_reasons = [
        f"{result.arm}:{result.status}"
        for result in [*legacy_results, *final_results]
        if result.status != "passed"
    ]
    if comparison.verdict == "regressed":
        blocking_regressions = _blocking_acceptance_regressions(comparison.regressed_metrics)
        if blocking_regressions:
            blocked_reasons.append("comparison_regressed:" + ",".join(blocking_regressions))
    acceptance_warnings = []
    if any(metric in _NON_BLOCKING_ACCEPTANCE_REGRESSIONS for metric in comparison.regressed_metrics):
        acceptance_warnings.append("non_blocking_latency_regression_observed")

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "source": "pir15_artifact_derived_normal_atlas_entrypoint_reports",
        "corpus_version": corpus["corpus_version"],
        "constraints": asdict(constraints),
        "task_count": len(tasks),
        "sample_count": {
            "legacy": len(legacy_results),
            "final": len(final_results),
        },
        "repetitions": {task.task_id: task.repetitions for task in tasks},
        "legacy": {
            "results": [asdict(result) for result in legacy_results],
            "average_metrics": legacy_arm.metrics,
        },
        "final": {
            "results": [asdict(result) for result in final_results],
            "average_metrics": final_arm.metrics,
        },
        "comparison": asdict(comparison),
        "acceptance": {
            "status": "passed" if not blocked_reasons else "blocked",
            "blocked_reasons": blocked_reasons,
            "warnings": acceptance_warnings,
            "observed_regressions": list(comparison.regressed_metrics),
        },
        "safety": {
            "manual_metrics_accepted": False,
            "normal_atlas_entrypoint_reports_required": True,
            "legacy_retirement": False,
            "rollout_transition": False,
        },
    }


def write_artifact_comparative_report(
    corpus_path: str | Path,
    output_path: str | Path,
    *,
    legacy_reports: dict[str, dict[str, Any]],
    final_reports: dict[str, dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    report = build_artifact_comparative_report(
        load_benchmark_corpus(corpus_path),
        legacy_reports=legacy_reports,
        final_reports=final_reports,
        generated_at=generated_at,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
