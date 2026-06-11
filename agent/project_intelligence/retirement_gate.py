"""PIR-15 active rollout and legacy retirement gate evidence.

The gate is read-only for source code and legacy paths. It can build an isolated
production-rollout preflight transition under a supplied data directory, then combines
that evidence with benchmark, cutover, registry, rollback, data-migration, and docs
signals. Legacy removal is ready only when every capability reaches consumer-zero.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.project_intelligence.production_factory import build_production_project_intelligence
from agent.project_intelligence.rollout import RolloutConfig


@dataclass(frozen=True)
class CapabilityRetirementStatus:
    capability: str
    legacy_consumer_count: int
    legacy_consumer_paths: list[str] = field(default_factory=list)
    consumer_zero: bool = False
    shadow_parity_passed: bool = False
    rollback_passed: bool = False
    cutover_ready: bool = False
    retirement_ready: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_active_rollout_transition_evidence(
    ca_data_dir: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Exercise off -> active production composition in an isolated data directory."""
    data_root = Path(ca_data_dir)
    off_service = build_production_project_intelligence(ca_data_dir=data_root, rollout=RolloutConfig.off())
    try:
        off_health = off_service.health()
    finally:
        off_service.close()

    active_service = build_production_project_intelligence(
        ca_data_dir=data_root,
        rollout=RolloutConfig(enabled=True),
    )
    try:
        active_health = active_service.health()
    finally:
        active_service.close()

    classes = active_health.get("preflight", {}).get("implementation_classes", {})
    disabled = {
        name: cls
        for name, cls in classes.items()
        if str(cls).startswith("Disabled")
    }
    transitions = list(active_health.get("rollout_state", {}).get("transitions") or [])
    active_transition_recorded = any(
        row.get("mode") == "active" and row.get("preflight_ok") is True
        for row in transitions
    )
    off_transition_recorded = any(row.get("mode") == "off" for row in transitions)
    passed = (
        off_health.get("rollout", {}).get("mode") == "off"
        and active_health.get("status") == "ok"
        and active_health.get("rollout", {}).get("mode") == "active"
        and not disabled
        and active_transition_recorded
    )
    return {
        "schema_version": 1,
        "generated_at": generated_at or _utcnow_iso(),
        "source": "pir15_isolated_production_rollout_preflight_transition",
        "ca_data_dir": str(data_root),
        "status": "passed" if passed else "blocked",
        "off_transition_recorded": off_transition_recorded,
        "active_transition_recorded": active_transition_recorded,
        "active_health": active_health,
        "disabled_modules": disabled,
        "safety": {
            "source_mutation": False,
            "legacy_retirement": False,
            "rollout_transition": passed,
            "automatic_rollout": False,
        },
    }


def _phase_status(rollout_evidence: dict[str, Any], phase: str | None) -> dict[str, str]:
    if phase is None:
        return {"shadow_parity_status": "not_required", "rollback_status": "not_required"}
    for entry in rollout_evidence.get("entries", []):
        if entry.get("phase") == phase:
            return {
                "shadow_parity_status": str(entry.get("shadow_parity_status") or "not_recorded"),
                "rollback_status": str(entry.get("rollback_status") or "not_recorded"),
            }
    return {"shadow_parity_status": "not_recorded", "rollback_status": "not_recorded"}


def _cutover_ready_by_phase(cutover_gate: dict[str, Any]) -> dict[str, bool]:
    return {
        str(entry.get("phase") or ""): bool(entry.get("cutover_ready"))
        for entry in cutover_gate.get("entries", [])
    }


def _capability_entries(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    capabilities: dict[str, dict[str, Any]] = {}
    for entry in registry.get("entries", []):
        capability = str(entry.get("capability") or "")
        if not capability:
            continue
        row = capabilities.setdefault(
            capability,
            {
                "legacy_consumer_paths": set(),
                "legacy_consumer_count": 0,
                "phases": set(),
            },
        )
        row["legacy_consumer_paths"].update(str(path) for path in entry.get("legacy_consumer_paths") or [])
        row["legacy_consumer_count"] = len(row["legacy_consumer_paths"]) or max(
            int(row["legacy_consumer_count"]),
            int(entry.get("legacy_consumer_count") or 0),
        )
        phase = entry.get("rollout_phase")
        if phase:
            row["phases"].add(str(phase))
    return capabilities


_REGISTRY_ENTRY_PHASES = {
    "planning_context": "planning",
    "generation_context": "generation",
    "impact_test_recommendation": "verification",
    "post_apply_refresh": "generation",
    "verification_ingest": "verification",
    "repair_replan_decisions": "repair",
    "final_completion": "verification",
    "greenfield_orchestration": "greenfield",
}


def _entry_phase(entry: dict[str, Any]) -> str | None:
    return _REGISTRY_ENTRY_PHASES.get(str(entry.get("name") or ""))


def _capability_statuses(
    registry: dict[str, Any],
    rollout_evidence: dict[str, Any],
    cutover_gate: dict[str, Any],
) -> list[CapabilityRetirementStatus]:
    capability_rows = _capability_entries(registry)
    cutover_by_phase = _cutover_ready_by_phase(cutover_gate)
    phase_map: dict[str, set[str | None]] = {}
    for entry in registry.get("entries", []):
        capability = str(entry.get("capability") or "")
        if capability:
            phase_map.setdefault(capability, set()).add(_entry_phase(entry))

    statuses: list[CapabilityRetirementStatus] = []
    for capability, row in sorted(capability_rows.items()):
        paths = sorted(row["legacy_consumer_paths"])
        legacy_count = int(row["legacy_consumer_count"])
        phases = phase_map.get(capability, {None})
        phase_statuses = [_phase_status(rollout_evidence, phase) for phase in phases]
        shadow_ok = all(
            status["shadow_parity_status"] in {"passed", "not_required"}
            for status in phase_statuses
        )
        rollback_ok = all(
            status["rollback_status"] in {"passed", "not_required"}
            for status in phase_statuses
        )
        cutover_ok = all(
            cutover_by_phase.get(phase, True) if phase is not None else True
            for phase in phases
        )
        reasons: list[str] = []
        if legacy_count != 0:
            reasons.append("legacy_consumers_remain")
        if not shadow_ok:
            reasons.append("shadow_parity_not_passed")
        if not rollback_ok:
            reasons.append("rollback_drill_not_passed")
        if not cutover_ok:
            reasons.append("cutover_gate_not_ready")
        ready = not reasons
        statuses.append(
            CapabilityRetirementStatus(
                capability=capability,
                legacy_consumer_count=legacy_count,
                legacy_consumer_paths=paths,
                consumer_zero=legacy_count == 0,
                shadow_parity_passed=shadow_ok,
                rollback_passed=rollback_ok,
                cutover_ready=cutover_ok,
                retirement_ready=ready,
                blocked_reasons=reasons,
            )
        )
    return statuses


def build_pir15_retirement_gate(
    *,
    benchmark_report: dict[str, Any],
    consumer_registry: dict[str, Any],
    rollout_evidence: dict[str, Any],
    consumer_cutover_gate: dict[str, Any],
    active_rollout_evidence: dict[str, Any],
    data_migration_verified: bool,
    docs_updated: bool,
    generated_at: str | None = None,
) -> dict[str, Any]:
    capability_statuses = _capability_statuses(consumer_registry, rollout_evidence, consumer_cutover_gate)
    benchmark_passed = benchmark_report.get("acceptance", {}).get("status") == "passed"
    manual_metrics_rejected = benchmark_report.get("safety", {}).get("manual_metrics_accepted") is False
    active_rollout_passed = active_rollout_evidence.get("status") == "passed"
    cutover_gate_passed = consumer_cutover_gate.get("summary", {}).get("gate_passed") is True
    all_capabilities_ready = all(status.retirement_ready for status in capability_statuses)
    blocked_reasons: list[str] = []
    if not benchmark_passed:
        blocked_reasons.append("benchmark_acceptance_not_passed")
    if not manual_metrics_rejected:
        blocked_reasons.append("manual_metric_rejection_not_proven")
    if not active_rollout_passed:
        blocked_reasons.append("active_rollout_transition_not_passed")
    if not cutover_gate_passed:
        blocked_reasons.append("consumer_cutover_gate_not_passed")
    if not data_migration_verified:
        blocked_reasons.append("data_migration_not_verified")
    if not docs_updated:
        blocked_reasons.append("docs_not_updated")
    if not all_capabilities_ready:
        blocked_reasons.append("legacy_capability_retirement_not_ready")

    gate_passed = not blocked_reasons
    return {
        "schema_version": 1,
        "generated_at": generated_at or _utcnow_iso(),
        "source": "pir15_retirement_gate_from_current_artifacts",
        "status": "passed" if gate_passed else "blocked",
        "inputs": {
            "benchmark_source": benchmark_report.get("source"),
            "registry_source": consumer_registry.get("source"),
            "rollout_evidence_source": rollout_evidence.get("source"),
            "cutover_gate_source": consumer_cutover_gate.get("source"),
            "active_rollout_source": active_rollout_evidence.get("source"),
        },
        "summary": {
            "benchmark_passed": benchmark_passed,
            "manual_metrics_rejected": manual_metrics_rejected,
            "active_rollout_passed": active_rollout_passed,
            "consumer_cutover_gate_passed": cutover_gate_passed,
            "data_migration_verified": data_migration_verified,
            "docs_updated": docs_updated,
            "capability_count": len(capability_statuses),
            "consumer_zero_capability_count": sum(1 for status in capability_statuses if status.consumer_zero),
            "retirement_ready_capability_count": sum(1 for status in capability_statuses if status.retirement_ready),
            "legacy_consumer_count": sum(status.legacy_consumer_count for status in capability_statuses),
            "blocked_reasons": blocked_reasons,
        },
        "capabilities": [asdict(status) for status in capability_statuses],
        "safety": {
            "source_mutation": False,
            "legacy_retirement": gate_passed,
            "deletion_authorized": gate_passed,
            "unavailable_counts_as_passed": False,
        },
    }


def write_active_rollout_transition_evidence(
    ca_data_dir: str | Path,
    output_path: str | Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    evidence = build_active_rollout_transition_evidence(ca_data_dir, generated_at=generated_at)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def write_pir15_retirement_gate(
    output_path: str | Path,
    *,
    benchmark_report_path: str | Path,
    consumer_registry_path: str | Path,
    rollout_evidence_path: str | Path,
    consumer_cutover_gate_path: str | Path,
    active_rollout_evidence_path: str | Path,
    data_migration_verified: bool = False,
    docs_updated: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    report = build_pir15_retirement_gate(
        benchmark_report=_load_json(benchmark_report_path),
        consumer_registry=_load_json(consumer_registry_path),
        rollout_evidence=_load_json(rollout_evidence_path),
        consumer_cutover_gate=_load_json(consumer_cutover_gate_path),
        active_rollout_evidence=_load_json(active_rollout_evidence_path),
        data_migration_verified=data_migration_verified,
        docs_updated=docs_updated,
        generated_at=generated_at,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
