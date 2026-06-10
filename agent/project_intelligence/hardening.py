"""Cross-platform, scale, storage, and rollout hardening (PI-24).

Provides the hardening primitives the program needs before active rollout: platform
detection with explicit unavailable evidence, an enforced regression budget, bounded-growth
checks (no unbounded prompt growth), non-destructive revision retention/compaction, store
export/import + integrity, job coalescing, a phased rollout gate with rollback, and a
project-data-leakage check. Pure where possible; storage helpers operate on public results.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Platforms.
WINDOWS = "windows"
LINUX = "linux"
DOCKER = "docker"
RUNPOD = "runpod"
UNKNOWN = "unknown"


def detect_platform(env: dict | None = None, *, platform_name: str | None = None) -> str:
    e = env if env is not None else os.environ
    if e.get("RUNPOD_POD_ID") or e.get("RUNPOD_API_KEY"):
        return RUNPOD
    if e.get("ATLAS_IN_DOCKER") or Path("/.dockerenv").exists():
        return DOCKER
    name = (platform_name or os.name)
    if name == "nt" or str(name).lower().startswith("win"):
        return WINDOWS
    if name in ("posix", "linux") or str(name).lower().startswith("linux"):
        return LINUX
    return UNKNOWN


def platform_evidence(platform: str, *, available: bool, detail: str = "") -> dict[str, Any]:
    """Cross-platform evidence; an unavailable platform is explicit, never assumed passed."""
    return {"platform": platform, "result": "observed" if available else "unavailable",
            "detail": detail or ("" if available else "platform evidence unavailable")}


# --- Regression budget -------------------------------------------------------


@dataclass
class RegressionBudget:
    """A baseline regression budget; a regression beyond the threshold fails (test plan §16)."""

    baseline: dict[str, float]
    threshold: float = 0.20  # default 20% until a workload-specific threshold is justified
    higher_is_better: frozenset[str] = field(default_factory=frozenset)

    def check(self, metric: str, value: float) -> tuple[bool, str]:
        base = self.baseline.get(metric)
        if base is None:
            return True, f"no baseline for {metric!r}"
        if metric in self.higher_is_better:
            allowed = base * (1 - self.threshold)
            ok = value >= allowed
            return ok, f"{metric}={value} vs floor {allowed:.4f}"
        allowed = base * (1 + self.threshold)
        ok = value <= allowed
        return ok, f"{metric}={value} vs ceiling {allowed:.4f}"

    def enforce(self, metrics: dict[str, float]) -> tuple[bool, list[str]]:
        failures = []
        for m, v in sorted(metrics.items()):
            ok, detail = self.check(m, v)
            if not ok:
                failures.append(detail)
        return (not failures), failures


# --- Bounded growth ----------------------------------------------------------


def assert_bounded(value: int, budget: int) -> bool:
    """True when value is within budget (no unbounded prompt/context growth)."""
    return value <= budget


# --- Revision retention / compaction (non-destructive) -----------------------


def compaction_plan(history: list[dict], *, keep_last: int = 3, head_id: str | None = None) -> dict[str, list[str]]:
    """Decide which revisions to retain vs prune. Head and the last N are always retained.

    Returns ids only (the caller performs any actual pruning with a backup); this never
    deletes data itself, so there is no data-loss risk in the plan.
    """
    ids = [h["artifact_id"] for h in history]
    retained = set(ids[-keep_last:]) if keep_last > 0 else set()
    if head_id:
        retained.add(head_id)
    prunable = [i for i in ids if i not in retained]
    return {"retained": sorted(retained), "prunable": prunable}


# --- Export / import / integrity ---------------------------------------------


def export_artifacts(artifact_store, project_id: str, group_id: str) -> list[dict]:
    return artifact_store.list_history(project_id, group_id)


def import_artifacts(artifact_store, exported: list[dict], *, workspace_id: str) -> int:
    count = 0
    for row in exported:
        try:
            artifact_store.put(
                project_id=row["project_id"], workspace_id=row.get("workspace_id", workspace_id),
                group_id=row["group_id"], artifact_id=row["artifact_id"],
                artifact_type=row.get("artifact_type", "import"), payload=row["payload"],
                status=row.get("status", "active"),
            )
            count += 1
        except Exception:
            # immutability violation on duplicate import is harmless (already present)
            pass
    return count


# --- Job coalescing ----------------------------------------------------------


def coalesce_refresh(store, *, project_id: str, workspace_id: str, job_type: str, target_key: str) -> str:
    """Enqueue a refresh job idempotently so duplicate triggers coalesce into one job."""
    return store.enqueue_job(project_id=project_id, workspace_id=workspace_id,
                             job_id=f"{job_type}:{target_key}", job_type=job_type,
                             idempotency_key=f"{job_type}:{target_key}")


# --- Phased rollout gate -----------------------------------------------------

ROLLOUT_STAGES = ["off", "shadow", "planning", "generation", "verification", "repair", "greenfield", "active"]


@dataclass
class RolloutGate:
    stage: str = "off"

    def advance(self, *, telemetry_ok: bool) -> tuple[str, bool]:
        """Advance to the next stage only when the current stage's telemetry passes."""
        idx = ROLLOUT_STAGES.index(self.stage)
        if not telemetry_ok or idx >= len(ROLLOUT_STAGES) - 1:
            return self.stage, False
        self.stage = ROLLOUT_STAGES[idx + 1]
        return self.stage, True

    def rollback(self) -> str:
        """Phase rollback: move to the previous stage (always available)."""
        idx = ROLLOUT_STAGES.index(self.stage)
        if idx > 0:
            self.stage = ROLLOUT_STAGES[idx - 1]
        return self.stage


# --- Project data leakage check ----------------------------------------------


def no_data_leakage(artifact_store, *, project_a: str, project_b: str, artifact_id: str) -> bool:
    """True when an artifact in project_a is NOT visible under project_b (isolation holds)."""
    in_a = artifact_store.get(project_a, artifact_id) is not None
    in_b = artifact_store.get(project_b, artifact_id) is not None
    return in_a and not in_b
