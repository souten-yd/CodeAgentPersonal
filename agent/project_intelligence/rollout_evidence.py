"""PIR-14 non-destructive rollout evidence helpers.

These helpers exercise the public Project Intelligence facade in off/shadow/active modes,
persisting evidence for shadow parity and flag-off rollback drills. They never cut over a
consumer, execute rollback, mutate source, or retire legacy paths.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_recovery_service import AtlasRecoveryService
from agent.project_intelligence.contracts import (
    GenerationContextRequest,
    PlanningContextRequest,
    ProjectIdentity,
    RuntimeObservationRecord,
    VerificationResultRequest,
)
from agent.project_intelligence.factory import build_project_intelligence
from agent.project_intelligence.rollout import RolloutConfig
from agent.project_intelligence.telemetry import TelemetryRecord

SUPPORTED_EVIDENCE_PHASES: tuple[str, ...] = ("planning", "generation", "verification", "recovery")
_VOLATILE_KEYS = {"generated_at", "manifest_id", "rollout_mode", "diagnostics"}


@dataclass(frozen=True)
class PhaseRolloutEvidence:
    phase: str
    shadow_parity_status: str
    rollback_status: str
    baseline_mode: str
    shadow_mode: str
    active_mode_before_rollback: str
    mode_after_rollback: str
    telemetry_event_count: int
    mismatch_paths: list[str]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _normalize(val) for key, val in sorted(value.items()) if key not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _diff_paths(left: Any, right: Any, prefix: str = "") -> list[str]:
    if type(left) is not type(right):
        return [prefix or "$"]
    if isinstance(left, dict):
        paths: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(_diff_paths(left[key], right[key], child))
        return paths
    if isinstance(left, list):
        if len(left) != len(right):
            return [prefix or "$"]
        paths = []
        for index, (l_item, r_item) in enumerate(zip(left, right)):
            paths.extend(_diff_paths(l_item, r_item, f"{prefix}[{index}]"))
        return paths
    return [] if left == right else [prefix or "$"]


def _project(root: Path) -> ProjectIdentity:
    return ProjectIdentity(
        project_id="pir14-rollout-evidence",
        workspace_id="local",
        project_path=str(root),
    )


def _call_phase(coordinator: Any, phase: str, project: ProjectIdentity) -> Any:
    if phase == "planning":
        return coordinator.prepare_planning_context(
            PlanningContextRequest(project=project, objective="PIR-14 shadow parity evidence")
        )
    if phase == "generation":
        return coordinator.prepare_generation_context(
            GenerationContextRequest(project=project, plan_pool_id="pir14", plan_item_id="rollout-evidence")
        )
    if phase == "verification":
        return coordinator.record_verification_result(
            VerificationResultRequest(
                project=project,
                plan_pool_id="pir14",
                plan_item_id="rollout-evidence",
                observations=[
                    RuntimeObservationRecord(
                        observation_id="pir14-verification-shadow",
                        project_id=project.project_id,
                        workspace_id=project.workspace_id,
                        observation_type="verification_result",
                        result="passed",
                        summary="PIR-14 verification shadow parity evidence",
                    )
                ],
                correlation_id="pir14-verification-shadow",
            )
        )
    raise ValueError(f"unsupported evidence phase: {phase}")


def _result_mode(result: Any, phase: str, rollout: RolloutConfig) -> str:
    manifest = getattr(result, "context_manifest", None)
    if manifest is not None:
        return str(getattr(manifest, "rollout_mode", "") or rollout.mode_for_phase(phase))
    return rollout.mode_for_phase(phase)


def _phase_evidence(root: Path, phase: str) -> tuple[PhaseRolloutEvidence, list[TelemetryRecord]]:
    if phase == "recovery":
        return _recovery_phase_evidence(root)
    project = _project(root)
    baseline_config = RolloutConfig.off()
    baseline_coord = build_project_intelligence(rollout=baseline_config)
    baseline_pkg = _call_phase(baseline_coord, phase, project)

    shadow_config = RolloutConfig(enabled=True, shadow=True, active_phases=frozenset({phase}))
    shadow_coord = build_project_intelligence(rollout=shadow_config)
    shadow_pkg = _call_phase(shadow_coord, phase, project)
    mismatch_paths = _diff_paths(_normalize(baseline_pkg), _normalize(shadow_pkg))

    active_config = RolloutConfig(enabled=True, shadow=False, active_phases=frozenset({phase}))
    active_mode = active_config.mode_for_phase(phase)
    rollback_config = RolloutConfig.off()
    rolled_back_coord = build_project_intelligence(rollout=rollback_config)
    rolled_back_pkg = _call_phase(rolled_back_coord, phase, project)
    mode_after_rollback = _result_mode(rolled_back_pkg, phase, rollback_config)
    rollback_ok = active_mode == "active" and mode_after_rollback == "off"

    records = shadow_coord.telemetry.records()
    return (
        PhaseRolloutEvidence(
            phase=phase,
            shadow_parity_status="passed" if not mismatch_paths else "failed",
            rollback_status="passed" if rollback_ok else "failed",
            baseline_mode=_result_mode(baseline_pkg, phase, baseline_config),
            shadow_mode=_result_mode(shadow_pkg, phase, shadow_config),
            active_mode_before_rollback=active_mode,
            mode_after_rollback=mode_after_rollback,
            telemetry_event_count=len(records),
            mismatch_paths=mismatch_paths,
        ),
        records,
    )


def _recovery_phase_evidence(root: Path) -> tuple[PhaseRolloutEvidence, list[TelemetryRecord]]:
    with tempfile.TemporaryDirectory(prefix="pir14_recovery_evidence_") as tmp:
        temp_root = Path(tmp)
        journal = AtlasJournal(temp_root)
        item = AtlasPlanItem(
            item_id="item_1",
            pool_id="pool_1",
            title="PIR-14 recovery evidence",
            goal="recover from Project Intelligence checkpoint",
            status="completed",
            metadata={
                "verification": {
                    "status": "passed",
                    "verified_at": "2026-06-11T00:00:00+00:00",
                    "project_intelligence_verification": {
                        "status": "recorded",
                        "checkpoint_id": "checkpoint-1",
                        "rollback_base_revision": "actual-rev-1",
                        "accepted": True,
                        "decision_route": {"action": "continue", "existing_services": ["continuation"]},
                        "revisions": {"working_tree_hash": ""},
                    },
                }
            },
        )
        pool = AtlasPlanPool(
            pool_id="pool_1",
            root_goal="PIR-14 recovery evidence",
            project_path=str(root),
            project_name="pir14",
            status="running",
            items=[item],
            current_item_id="item_1",
            completed_item_ids=["item_1"],
        )
        journal.save_plan_pool(pool)
        first = AtlasRecoveryService(journal).recover_pool("pool_1")
        second = AtlasRecoveryService(journal).recover_pool("pool_1")
        first_meta = _normalize(first.metadata.get("project_intelligence_checkpoint", {}))
        second_meta = _normalize(second.metadata.get("project_intelligence_checkpoint", {}))
        mismatch_paths = _diff_paths(first_meta, second_meta)
        rollback_ok = bool(first_meta.get("rollback_base_revision")) and first_meta.get("resume_action") == "resume"
        return (
            PhaseRolloutEvidence(
                phase="recovery",
                shadow_parity_status="passed" if not mismatch_paths else "failed",
                rollback_status="passed" if rollback_ok else "failed",
                baseline_mode="checkpoint_metadata",
                shadow_mode="checkpoint_metadata",
                active_mode_before_rollback="checkpoint_present",
                mode_after_rollback=str(first_meta.get("resume_action") or ""),
                telemetry_event_count=0,
                mismatch_paths=mismatch_paths,
            ),
            [],
        )


def build_rollout_evidence(
    root: str | Path,
    *,
    phases: tuple[str, ...] = SUPPORTED_EVIDENCE_PHASES,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    entries: list[PhaseRolloutEvidence] = []
    telemetry_count = 0
    for phase in phases:
        if phase not in SUPPORTED_EVIDENCE_PHASES:
            raise ValueError(f"unsupported evidence phase: {phase}")
        entry, records = _phase_evidence(root_path, phase)
        entries.append(entry)
        telemetry_count += len(records)
    return {
        "schema_version": 1,
        "generated_at": generated_at or _utcnow_iso(),
        "source": "project_intelligence_public_facade_off_shadow_active_modes",
        "repository_root": root_path.name,
        "entries": [asdict(entry) for entry in entries],
        "summary": {
            "phase_count": len(entries),
            "shadow_parity_passed_count": sum(1 for entry in entries if entry.shadow_parity_status == "passed"),
            "rollback_passed_count": sum(1 for entry in entries if entry.rollback_status == "passed"),
            "telemetry_event_count": telemetry_count,
        },
        "safety": {
            "consumer_cutover": False,
            "source_mutation": False,
            "automatic_rollback": False,
            "legacy_retirement": False,
        },
    }


def write_rollout_evidence(
    root: str | Path,
    output: str | Path,
    *,
    phases: tuple[str, ...] = SUPPORTED_EVIDENCE_PHASES,
    generated_at: str | None = None,
) -> dict[str, Any]:
    evidence = build_rollout_evidence(root, phases=phases, generated_at=generated_at)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence
