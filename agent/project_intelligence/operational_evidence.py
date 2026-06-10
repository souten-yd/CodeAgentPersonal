"""PIR-14 operational evidence artifact.

Captures current-platform evidence, explicit unavailable platform rows, bounded current
checkout scale metrics, and threshold-driven rollout phase rollback decisions. This is
evidence collection only; it does not run a platform matrix, cut over consumers, mutate
source, or retire legacy paths.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.project_intelligence.hardening import (
    DOCKER,
    LINUX,
    RUNPOD,
    WINDOWS,
    RegressionBudget,
    RolloutGate,
    assert_bounded,
    detect_platform,
    platform_evidence,
)

SUPPORTED_PLATFORMS: tuple[str, ...] = (WINDOWS, LINUX, DOCKER, RUNPOD)


@dataclass(frozen=True)
class ScaleEvidence:
    metric: str
    value: int
    budget: int
    result: str
    detail: str


@dataclass(frozen=True)
class ThresholdRollbackEvidence:
    start_stage: str
    metrics: dict[str, float]
    threshold_ok: bool
    failures: list[str]
    rolled_back: bool
    final_stage: str


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _count_python_files(root: Path) -> int:
    total = 0
    for base in ("agent", "app", "tests"):
        start = root / base
        if not start.exists():
            continue
        total += sum(1 for path in start.rglob("*.py") if "__pycache__" not in path.parts)
    return total


def _platform_rows(current_platform: str) -> list[dict[str, Any]]:
    rows = []
    for platform in SUPPORTED_PLATFORMS:
        available = platform == current_platform
        detail = "current runner platform observed" if available else "platform job not executed in this slice"
        rows.append(platform_evidence(platform, available=available, detail=detail))
    return rows


def _threshold_rollback(start_stage: str, metrics: dict[str, float]) -> ThresholdRollbackEvidence:
    budget = RegressionBudget(baseline={"latency_ms": 100.0}, threshold=0.20)
    threshold_ok, failures = budget.enforce(metrics)
    gate = RolloutGate(stage=start_stage)
    final_stage = gate.stage
    rolled_back = False
    if not threshold_ok:
        final_stage = gate.rollback()
        rolled_back = final_stage != start_stage
    return ThresholdRollbackEvidence(
        start_stage=start_stage,
        metrics=dict(metrics),
        threshold_ok=threshold_ok,
        failures=failures,
        rolled_back=rolled_back,
        final_stage=final_stage,
    )


def build_operational_evidence(
    root: str | Path,
    *,
    env: dict | None = None,
    platform_name: str | None = None,
    generated_at: str | None = None,
    file_budget: int = 5000,
    threshold_metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    current_platform = detect_platform(env, platform_name=platform_name)
    python_file_count = _count_python_files(root_path)
    scale_ok = assert_bounded(python_file_count, file_budget)
    rollback = _threshold_rollback("generation", threshold_metrics or {"latency_ms": 130.0})
    return {
        "schema_version": 1,
        "generated_at": generated_at or _utcnow_iso(),
        "source": "project_intelligence_operational_evidence_current_checkout",
        "repository_root": root_path.name,
        "current_platform": current_platform,
        "platform_evidence": _platform_rows(current_platform),
        "scale_evidence": [
            asdict(
                ScaleEvidence(
                    metric="python_file_count",
                    value=python_file_count,
                    budget=file_budget,
                    result="passed" if scale_ok else "failed",
                    detail="current checkout bounded-growth sample; not a large-repository benchmark",
                )
            )
        ],
        "threshold_rollback": asdict(rollback),
        "summary": {
            "observed_platform_count": sum(1 for row in _platform_rows(current_platform) if row["result"] == "observed"),
            "unavailable_platform_count": sum(
                1 for row in _platform_rows(current_platform) if row["result"] == "unavailable"
            ),
            "scale_passed_count": 1 if scale_ok else 0,
            "threshold_rollback_triggered": rollback.rolled_back,
        },
        "safety": {
            "platform_matrix_claimed": False,
            "large_repository_benchmark_claimed": False,
            "consumer_cutover": False,
            "source_mutation": False,
            "legacy_retirement": False,
        },
    }


def write_operational_evidence(
    root: str | Path,
    output: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    evidence = build_operational_evidence(root, **kwargs)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence
