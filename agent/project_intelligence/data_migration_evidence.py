"""PIR-15 data-migration verification evidence.

The verifier is read-only. It proves that migration state is derived from the
current registry and rollout artifacts before the retirement gate may authorize
legacy deletion in a later, separate change.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactCheck:
    name: str
    path: str
    exists: bool
    json_valid: bool
    passed: bool
    blocked_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CapabilityMigrationCheck:
    capability: str
    registry_entry_count: int
    legacy_consumer_count: int
    legacy_consumer_paths: list[str] = field(default_factory=list)
    facade_entrypoints: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    consumer_zero: bool = False
    migration_verified: bool = False
    blocked_reasons: list[str] = field(default_factory=list)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: str | Path) -> tuple[dict[str, Any] | None, ArtifactCheck]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return None, ArtifactCheck(
            name=artifact_path.name,
            path=str(artifact_path),
            exists=False,
            json_valid=False,
            passed=False,
            blocked_reasons=["artifact_missing"],
        )
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, ArtifactCheck(
            name=artifact_path.name,
            path=str(artifact_path),
            exists=True,
            json_valid=False,
            passed=False,
            blocked_reasons=["artifact_json_invalid"],
        )
    return payload, ArtifactCheck(
        name=artifact_path.name,
        path=str(artifact_path),
        exists=True,
        json_valid=True,
        passed=True,
        blocked_reasons=[],
    )


def _registry_capabilities(registry: dict[str, Any]) -> list[CapabilityMigrationCheck]:
    capabilities: dict[str, dict[str, Any]] = {}
    for entry in registry.get("entries", []):
        capability = str(entry.get("capability") or "")
        if not capability:
            continue
        row = capabilities.setdefault(
            capability,
            {
                "entry_count": 0,
                "legacy_consumer_paths": set(),
                "legacy_consumer_count": 0,
                "facade_entrypoints": set(),
                "owners": set(),
            },
        )
        row["entry_count"] += 1
        row["legacy_consumer_count"] += int(entry.get("legacy_consumer_count") or 0)
        row["legacy_consumer_paths"].update(str(path) for path in entry.get("legacy_consumer_paths") or [])
        facade = str(entry.get("facade_entrypoint") or "")
        if facade:
            row["facade_entrypoints"].add(facade)
        owner = str(entry.get("owner") or "")
        if owner:
            row["owners"].add(owner)

    checks: list[CapabilityMigrationCheck] = []
    for capability, row in sorted(capabilities.items()):
        paths = sorted(row["legacy_consumer_paths"])
        count = int(row["legacy_consumer_count"])
        reasons: list[str] = []
        if count != 0 or paths:
            reasons.append("legacy_consumers_remain")
        if not row["facade_entrypoints"]:
            reasons.append("facade_entrypoint_missing")
        if not row["owners"]:
            reasons.append("owner_missing")
        checks.append(
            CapabilityMigrationCheck(
                capability=capability,
                registry_entry_count=int(row["entry_count"]),
                legacy_consumer_count=count,
                legacy_consumer_paths=paths,
                facade_entrypoints=sorted(row["facade_entrypoints"]),
                owners=sorted(row["owners"]),
                consumer_zero=count == 0 and not paths,
                migration_verified=not reasons,
                blocked_reasons=reasons,
            )
        )
    return checks


def _required_phase_count(rollout_evidence: dict[str, Any]) -> int:
    return len({str(entry.get("phase") or "") for entry in rollout_evidence.get("entries", []) if entry.get("phase")})


def build_pir15_data_migration_evidence(
    *,
    benchmark_report_path: str | Path,
    consumer_registry_path: str | Path,
    rollout_evidence_path: str | Path,
    consumer_cutover_gate_path: str | Path,
    active_rollout_evidence_path: str | Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    benchmark, benchmark_check = _load_json(benchmark_report_path)
    registry, registry_check = _load_json(consumer_registry_path)
    rollout_evidence, rollout_check = _load_json(rollout_evidence_path)
    cutover_gate, cutover_check = _load_json(consumer_cutover_gate_path)
    active_rollout, active_rollout_check = _load_json(active_rollout_evidence_path)
    artifact_checks = [benchmark_check, registry_check, rollout_check, cutover_check, active_rollout_check]

    blocked_reasons: list[str] = []
    if any(not check.passed for check in artifact_checks):
        blocked_reasons.append("required_artifact_unavailable")

    benchmark_passed = bool(benchmark and benchmark.get("acceptance", {}).get("status") == "passed")
    manual_metrics_rejected = bool(benchmark and benchmark.get("safety", {}).get("manual_metrics_accepted") is False)
    if not benchmark_passed:
        blocked_reasons.append("benchmark_acceptance_not_passed")
    if not manual_metrics_rejected:
        blocked_reasons.append("manual_metrics_rejection_not_proven")

    registry_entries = list(registry.get("entries", []) if registry else [])
    registry_legacy_count = int(registry.get("summary", {}).get("legacy_consumer_count") or 0) if registry else 0
    registry_parse_errors = list(registry.get("parse_errors") or []) if registry else []
    capability_checks = _registry_capabilities(registry or {})
    if not registry_entries:
        blocked_reasons.append("consumer_registry_empty")
    if registry_legacy_count != 0:
        blocked_reasons.append("consumer_registry_legacy_consumers_remain")
    if registry_parse_errors:
        blocked_reasons.append("consumer_registry_parse_errors")
    if any(not check.migration_verified for check in capability_checks):
        blocked_reasons.append("capability_migration_not_verified")

    phase_count = _required_phase_count(rollout_evidence or {})
    rollout_summary = rollout_evidence.get("summary", {}) if rollout_evidence else {}
    rollout_safety = rollout_evidence.get("safety", {}) if rollout_evidence else {}
    rollout_passed = (
        phase_count >= 6
        and int(rollout_summary.get("shadow_parity_passed_count") or 0) >= phase_count
        and int(rollout_summary.get("rollback_passed_count") or 0) >= phase_count
        and rollout_safety.get("source_mutation") is False
        and rollout_safety.get("legacy_retirement") is False
        and rollout_safety.get("consumer_cutover") is False
    )
    if not rollout_passed:
        blocked_reasons.append("rollout_shadow_or_rollback_evidence_incomplete")

    cutover_summary = cutover_gate.get("summary", {}) if cutover_gate else {}
    cutover_safety = cutover_gate.get("safety", {}) if cutover_gate else {}
    cutover_passed = (
        cutover_summary.get("gate_passed") is True
        and cutover_safety.get("source_mutation") is False
        and cutover_safety.get("legacy_retirement") is False
    )
    if not cutover_passed:
        blocked_reasons.append("consumer_cutover_gate_not_passed")

    active_rollout_safety = active_rollout.get("safety", {}) if active_rollout else {}
    active_rollout_passed = (
        bool(active_rollout and active_rollout.get("status") == "passed")
        and active_rollout_safety.get("source_mutation") is False
        and active_rollout_safety.get("legacy_retirement") is False
    )
    if not active_rollout_passed:
        blocked_reasons.append("active_rollout_transition_not_passed")

    data_migration_verified = not blocked_reasons
    return {
        "schema_version": 1,
        "generated_at": generated_at or _utcnow_iso(),
        "source": "pir15_data_migration_from_current_artifacts",
        "status": "passed" if data_migration_verified else "blocked",
        "artifact_checks": [asdict(check) for check in artifact_checks],
        "capabilities": [asdict(check) for check in capability_checks],
        "summary": {
            "data_migration_verified": data_migration_verified,
            "benchmark_passed": benchmark_passed,
            "manual_metrics_rejected": manual_metrics_rejected,
            "consumer_registry_entry_count": len(registry_entries),
            "consumer_registry_legacy_count": registry_legacy_count,
            "capability_count": len(capability_checks),
            "consumer_zero_capability_count": sum(1 for check in capability_checks if check.consumer_zero),
            "rollout_phase_count": phase_count,
            "rollout_shadow_and_rollback_passed": rollout_passed,
            "consumer_cutover_gate_passed": cutover_passed,
            "active_rollout_passed": active_rollout_passed,
            "blocked_reasons": blocked_reasons,
        },
        "safety": {
            "source_mutation": False,
            "legacy_retirement": False,
            "deletion_authorized": False,
            "manual_flag_accepted": False,
            "unavailable_counts_as_passed": False,
        },
    }


def write_pir15_data_migration_evidence(
    output_path: str | Path,
    *,
    benchmark_report_path: str | Path,
    consumer_registry_path: str | Path,
    rollout_evidence_path: str | Path,
    consumer_cutover_gate_path: str | Path,
    active_rollout_evidence_path: str | Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    evidence = build_pir15_data_migration_evidence(
        benchmark_report_path=benchmark_report_path,
        consumer_registry_path=consumer_registry_path,
        rollout_evidence_path=rollout_evidence_path,
        consumer_cutover_gate_path=consumer_cutover_gate_path,
        active_rollout_evidence_path=active_rollout_evidence_path,
        generated_at=generated_at,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence
