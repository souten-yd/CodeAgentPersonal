"""PIR-14 source-derived consumer registry and rollout telemetry artifact.

The registry is generated from the current checkout plus runtime telemetry records. It is
advisory evidence for phased cutover decisions; it does not authorize mutation, rollout,
legacy deletion, or automatic rollback.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agent.project_intelligence.inspection.consumer_inventory import (
    LEGACY_CAPABILITY_MODULES,
    build_inventory,
)
from agent.project_intelligence.rollout import RolloutConfig
from agent.project_intelligence.telemetry import TelemetryRecord


@dataclass(frozen=True)
class ConsumerPhaseSpec:
    name: str
    capability: str
    rollout_phase: str | None
    legacy_entrypoint: str
    facade_entrypoint: str
    owner: str
    tests: tuple[str, ...]


@dataclass(frozen=True)
class ConsumerRegistryEntry:
    name: str
    capability: str
    legacy_entrypoint: str
    facade_entrypoint: str
    current_mode: str
    call_count: int
    telemetry_event_count: int
    shadow_parity_status: str
    rollback_status: str
    legacy_consumer_count: int
    legacy_consumer_paths: list[str] = field(default_factory=list)
    owner: str = ""
    tests: list[str] = field(default_factory=list)


CUTOVER_PHASES: tuple[ConsumerPhaseSpec, ...] = (
    ConsumerPhaseSpec(
        name="read_only_inspection",
        capability="legacy_project_inspection",
        rollout_phase=None,
        legacy_entrypoint="AtlasProjectInspectionService / AtlasGitInspectionService",
        facade_entrypoint="ProjectIntelligenceModule / DigitalTwinModule public query",
        owner="app/api/atlas_dev_tools.py",
        tests=("tests/test_project_intelligence_contracts.py",),
    ),
    ConsumerPhaseSpec(
        name="planning_context",
        capability="legacy_planner_context",
        rollout_phase="planning",
        legacy_entrypoint="AtlasRepoContextPlannerPackager / AtlasPlannerPackagingV2Service",
        facade_entrypoint="ProjectIntelligenceModule.prepare_planning_context",
        owner="agent/project_intelligence/adapters/atlas_planning.py",
        tests=("tests/test_project_intelligence_planner_bridge.py",),
    ),
    ConsumerPhaseSpec(
        name="generation_context",
        capability="legacy_planner_context",
        rollout_phase="generation",
        legacy_entrypoint="ContextBuilder / AtlasGeneratorBridge legacy context",
        facade_entrypoint="ProjectIntelligenceModule.prepare_generation_context",
        owner="agent/project_intelligence/adapters/atlas_generation.py",
        tests=("tests/test_project_intelligence_generator_bridge.py",),
    ),
    ConsumerPhaseSpec(
        name="impact_test_recommendation",
        capability="legacy_verification_recommendation",
        rollout_phase="verification",
        legacy_entrypoint="AtlasVerificationRecommendationService",
        facade_entrypoint="ProjectIntelligenceModule verification context and Convergence reports",
        owner="app/api/atlas_repo_context.py",
        tests=("tests/test_project_intelligence_pir12_verification_recovery.py",),
    ),
    ConsumerPhaseSpec(
        name="post_apply_refresh",
        capability="legacy_context_refresh",
        rollout_phase="generation",
        legacy_entrypoint="AtlasContextRefreshService / AtlasContextRefreshV2Service",
        facade_entrypoint="ProjectIntelligenceModule.record_apply_result",
        owner="agent/project_intelligence/coordinator.py",
        tests=("tests/test_project_intelligence_pir11_generation_apply.py",),
    ),
    ConsumerPhaseSpec(
        name="verification_ingest",
        capability="legacy_verification_gate",
        rollout_phase="verification",
        legacy_entrypoint="AtlasVerificationGateService and canonical verification outcomes",
        facade_entrypoint="ProjectIntelligenceModule.record_verification_result",
        owner="agent/project_intelligence/adapters/atlas_verification.py",
        tests=("tests/test_project_intelligence_pir12_verification_recovery.py",),
    ),
    ConsumerPhaseSpec(
        name="repair_replan_decisions",
        capability="legacy_verification_recommendation",
        rollout_phase="repair",
        legacy_entrypoint="AtlasVerificationRecommendationHandoffService repair/replan advice",
        facade_entrypoint="ProjectIntelligenceModule + Convergence bounded advisory decisions",
        owner="agent/project_intelligence/adapters/atlas_generation.py",
        tests=("tests/test_project_intelligence_generator_bridge.py",),
    ),
    ConsumerPhaseSpec(
        name="final_completion",
        capability="legacy_context_refresh",
        rollout_phase="verification",
        legacy_entrypoint="legacy completion rollups over context/verification artifacts",
        facade_entrypoint="ProjectIntelligence completion gate over canonical evidence",
        owner="agent/project_intelligence/completion.py",
        tests=("tests/test_project_intelligence_completion.py",),
    ),
    ConsumerPhaseSpec(
        name="greenfield_orchestration",
        capability="legacy_repo_context",
        rollout_phase="greenfield",
        legacy_entrypoint="Greenfield orchestration legacy repository context",
        facade_entrypoint="ProjectIntelligence Greenfield state machine and normal Atlas entrypoint",
        owner="agent/project_intelligence/greenfield.py",
        tests=("tests/test_project_intelligence_pir13_entrypoint_scenarios.py",),
    ),
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _legacy_by_capability(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "paths": set()})
    for legacy in inventory.get("legacy_consumers", []):
        capability = str(legacy.get("capability") or "")
        rows[capability]["count"] += int(legacy.get("production_consumer_count") or 0)
        for consumer in legacy.get("production_consumers") or []:
            path = consumer.get("path")
            if path:
                rows[capability]["paths"].add(str(path))
    return rows


def _telemetry_by_phase(records: Iterable[TelemetryRecord]) -> tuple[Counter[str], dict[str, list[TelemetryRecord]]]:
    counts: Counter[str] = Counter()
    by_phase: dict[str, list[TelemetryRecord]] = defaultdict(list)
    for record in records:
        counts[record.phase] += 1
        by_phase[record.phase].append(record)
    return counts, by_phase


def _shadow_status(records: list[TelemetryRecord]) -> str:
    shadow_records = [record for record in records if record.event_type == "shadow_comparison"]
    if not shadow_records:
        return "not_recorded"
    if any(record.detail.get("parity") is False for record in shadow_records):
        return "mismatch_recorded"
    if any(record.detail.get("parity") is True for record in shadow_records):
        return "parity_passed"
    return "shadow_observed_no_parity_decision"


def _rollback_status(records: list[TelemetryRecord]) -> str:
    rollback_records = [record for record in records if record.event_type == "rollback_drill"]
    if any(record.detail.get("result") == "passed" for record in rollback_records):
        return "rollback_drill_passed"
    if rollback_records:
        return "rollback_drill_failed_or_incomplete"
    return "flag_off_available_not_drilled"


def build_consumer_registry(
    root: str | Path,
    *,
    telemetry_records: Iterable[TelemetryRecord] = (),
    rollout: RolloutConfig | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a PIR-14 registry from current source and supplied runtime telemetry."""
    root_path = Path(root).resolve()
    inventory = build_inventory(root_path)
    config = rollout or RolloutConfig.off()
    legacy = _legacy_by_capability(inventory)
    telemetry_counts, telemetry_by_phase = _telemetry_by_phase(list(telemetry_records))

    entries: list[ConsumerRegistryEntry] = []
    for spec in CUTOVER_PHASES:
        phase_records = telemetry_by_phase.get(spec.rollout_phase or spec.name, [])
        legacy_row = legacy.get(spec.capability, {"count": 0, "paths": set()})
        mode = config.mode_for_phase(spec.rollout_phase) if spec.rollout_phase else "off"
        entries.append(
            ConsumerRegistryEntry(
                name=spec.name,
                capability=spec.capability,
                legacy_entrypoint=spec.legacy_entrypoint,
                facade_entrypoint=spec.facade_entrypoint,
                current_mode=mode,
                call_count=telemetry_counts.get(spec.rollout_phase or spec.name, 0),
                telemetry_event_count=len(phase_records),
                shadow_parity_status=_shadow_status(phase_records),
                rollback_status=_rollback_status(phase_records),
                legacy_consumer_count=int(legacy_row["count"]),
                legacy_consumer_paths=sorted(legacy_row["paths"]),
                owner=spec.owner,
                tests=list(spec.tests),
            )
        )

    return {
        "schema_version": 1,
        "generated_at": generated_at or _utcnow_iso(),
        "source": "python_ast_current_checkout_plus_runtime_telemetry",
        "repository_root": root_path.name,
        "rollout_mode": config.mode(),
        "known_legacy_modules": sorted(LEGACY_CAPABILITY_MODULES),
        "entries": [asdict(entry) for entry in entries],
        "summary": {
            "entry_count": len(entries),
            "legacy_consumer_count": sum(entry.legacy_consumer_count for entry in entries),
            "telemetry_event_count": sum(entry.telemetry_event_count for entry in entries),
            "active_entry_count": sum(1 for entry in entries if entry.current_mode == "active"),
            "shadow_entry_count": sum(1 for entry in entries if entry.current_mode == "shadow"),
            "rollback_drill_passed_count": sum(
                1 for entry in entries if entry.rollback_status == "rollback_drill_passed"
            ),
        },
        "inventory_summary": inventory.get("summary", {}),
        "parse_errors": inventory.get("parse_errors", []),
        "safety": {
            "mutation_authority": False,
            "automatic_rollout": False,
            "automatic_rollback": False,
            "legacy_retirement": False,
        },
    }


def write_consumer_registry(
    root: str | Path,
    output: str | Path,
    *,
    telemetry_records: Iterable[TelemetryRecord] = (),
    rollout: RolloutConfig | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Persist the generated registry as a deterministic JSON artifact."""
    registry = build_consumer_registry(
        root,
        telemetry_records=telemetry_records,
        rollout=rollout,
        generated_at=generated_at,
    )
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return registry
