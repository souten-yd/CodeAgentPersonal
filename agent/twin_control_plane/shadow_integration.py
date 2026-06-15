"""Atlas pipeline shadow integration (TFG-11 / Package 10).

Assembles the Twin/Forge/Git Steward components into a single shadow report that the
Atlas pipeline can produce *alongside* legacy execution, without taking it over.

Three hard invariants, mirroring the existing Forge shadow store:

- OFF mode is unchanged: ``assemble`` in ``OFF`` mode returns ``None`` and touches
  nothing, so a caller that leaves the orchestrator off behaves exactly as before;
- SHADOW mode produces ExecutionPolicy, TwinBrief, a local Git plan, and BlastMap /
  TwinProof reports *where the inputs allow it*, and records what it could not build as
  ``unavailable`` rather than raising — an unavailable shadow report never breaks the
  legacy flow;
- shadow never changes execution or production routing: the report is advisory evidence
  only (``changes_execution`` / ``changes_production_routing`` are always False).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterable

from pydantic import Field

from agent.git_steward.contracts import GitOperationDecision, classify_git_operation
from agent.project_intelligence.contracts import RuntimeObservationRecord
from agent.project_twin.contracts import ImpactResult
from agent.twin_control_plane.blast_map import BlastMap, build_blast_map
from agent.twin_control_plane.contracts import (
    ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION,
    ExecutionPolicy,
    TwinBrief,
    TwinControlPlaneModel,
)
from agent.twin_control_plane.twinproof import TwinProofReport, build_twinproof

# Local Git operations a shadow plan may describe (never remote publication/admin).
_DEFAULT_GIT_PLAN: tuple[str, ...] = ("status", "branch", "add", "commit", "diff")


class TwinShadowMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"


class TwinShadowReport(TwinControlPlaneModel):
    schema_version: str = ATLAS_TWIN_CONTROL_PLANE_CONTRACT_VERSION
    report_id: str = Field(min_length=1)
    mode: TwinShadowMode = TwinShadowMode.SHADOW
    requirement_ref: str = ""
    plan_item_ref: str = ""
    execution_policy: ExecutionPolicy | None = None
    twin_brief: TwinBrief | None = None
    git_plan: list[GitOperationDecision] = Field(default_factory=list)
    blast_map: BlastMap | None = None
    twinproof: TwinProofReport | None = None
    # Artifacts that could not be assembled from the supplied inputs.
    unavailable_artifacts: list[str] = Field(default_factory=list)
    # Shadow is advisory evidence only — it never takes over execution or routing.
    changes_execution: bool = False
    changes_production_routing: bool = False
    assembled_at: str = ""


def _git_plan(operations: Iterable[str]) -> tuple[list[GitOperationDecision], list[str]]:
    decisions: list[GitOperationDecision] = []
    unavailable: list[str] = []
    for op in operations:
        decision = classify_git_operation(op)
        # A shadow plan describes local autonomy only; anything needing approval is
        # recorded as unavailable for autonomous shadow rather than silently planned.
        if decision.approval_required:
            unavailable.append(f"git_plan:{op}:approval_required")
            continue
        decisions.append(decision)
    return decisions, unavailable


class TwinShadowOrchestrator:
    """Assemble shadow artifacts without changing legacy execution.

    The orchestrator takes already-built component inputs (the Atlas pipeline owns how
    they are produced) and composes the cross-cutting BlastMap/TwinProof/Git plan, so it
    stays dependency-light and never re-runs Twin analysis itself."""

    def __init__(
        self,
        mode: TwinShadowMode = TwinShadowMode.OFF,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._mode = TwinShadowMode(mode)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def mode(self) -> TwinShadowMode:
        return self._mode

    def assemble(
        self,
        *,
        requirement_ref: str = "",
        plan_item_ref: str = "",
        execution_policy: ExecutionPolicy | None = None,
        twin_brief: TwinBrief | None = None,
        impact: ImpactResult | None = None,
        changed_refs: Iterable[str] = (),
        git_operations: Iterable[str] | None = None,
        runtime_observations: Iterable[RuntimeObservationRecord] = (),
        related_test_refs: Iterable[str] = (),
        stale_test_refs: Iterable[str] = (),
    ) -> TwinShadowReport | None:
        """Assemble a shadow report. Returns ``None`` in OFF mode (legacy unchanged)."""
        if self._mode == TwinShadowMode.OFF:
            return None

        unavailable: list[str] = []

        blast_map: BlastMap | None = None
        if impact is not None:
            blast_map = build_blast_map(impact, brief=twin_brief, changed_refs=changed_refs)
        else:
            unavailable.append("blast_map:no_impact_result")

        impacted_refs = list(blast_map.changed_refs) if blast_map else list(
            twin_brief.impacted_refs if twin_brief else []
        )
        twinproof = build_twinproof(
            runtime_observations=runtime_observations,
            related_test_refs=related_test_refs,
            impacted_refs=impacted_refs,
            stale_test_refs=stale_test_refs,
        )
        if not twinproof.test_inventory and not twinproof.proof_gaps:
            unavailable.append("twinproof:no_runtime_or_test_evidence")

        ops = list(git_operations) if git_operations is not None else list(_DEFAULT_GIT_PLAN)
        git_plan, git_unavailable = _git_plan(ops)
        unavailable.extend(git_unavailable)

        if execution_policy is None:
            unavailable.append("execution_policy:not_supplied")
        if twin_brief is None:
            unavailable.append("twin_brief:not_supplied")

        report_id = "twin_shadow:" + (plan_item_ref or requirement_ref or "unscoped")
        return TwinShadowReport(
            report_id=report_id,
            mode=self._mode,
            requirement_ref=requirement_ref,
            plan_item_ref=plan_item_ref,
            execution_policy=execution_policy,
            twin_brief=twin_brief,
            git_plan=git_plan,
            blast_map=blast_map,
            twinproof=twinproof,
            unavailable_artifacts=unavailable,
            assembled_at=self._clock().isoformat(),
        )


class TwinShadowStore:
    """Persist shadow reports as advisory evidence (never touches live state)."""

    def __init__(self, store_dir: str | Path) -> None:
        self._dir = Path(store_dir)

    def _safe_name(self, report: TwinShadowReport) -> str:
        return report.report_id.replace(":", "_").replace("/", "_") + ".shadow.json"

    def record(self, report: TwinShadowReport) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / self._safe_name(report)
        path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(path)

    def load(self, report_id: str) -> TwinShadowReport | None:
        name = report_id.replace(":", "_").replace("/", "_") + ".shadow.json"
        path = self._dir / name
        if not path.exists():
            return None
        return TwinShadowReport.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "TwinShadowMode",
    "TwinShadowReport",
    "TwinShadowOrchestrator",
    "TwinShadowStore",
]
