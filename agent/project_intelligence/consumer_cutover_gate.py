"""PIR-14 consumer cutover evidence gate.

The gate audits whether required Atlas production consumers are connected to Project
Intelligence facades and whether the evidence required to cut them over is present. It is
read-only: failing or passing the gate does not switch rollout modes, mutate source, or
retire legacy paths.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProductionConsumerSpec:
    name: str
    phase: str
    path: str
    markers: tuple[str, ...]
    evidence_tests: tuple[str, ...]


@dataclass(frozen=True)
class ProductionConsumerEvidence:
    name: str
    phase: str
    path: str
    production_connected: bool
    missing_markers: list[str] = field(default_factory=list)
    evidence_tests: list[str] = field(default_factory=list)


REQUIRED_PRODUCTION_CONSUMERS: tuple[ProductionConsumerSpec, ...] = (
    ProductionConsumerSpec(
        name="planning",
        phase="planning",
        path="app/api/atlas_pipeline.py",
        markers=(
            "ProjectIntelligencePlannerBridge",
            "_project_intelligence_planning_metadata",
            "get_project_intelligence_service",
        ),
        evidence_tests=("tests/test_atlas_api_pipeline.py",),
    ),
    ProductionConsumerSpec(
        name="generation",
        phase="generation",
        path="agent/atlas_patch_proposal_service.py",
        markers=(
            "AtlasGeneratorBridge",
            "_attach_project_intelligence_generation_context",
            "project_intelligence_generation",
        ),
        evidence_tests=("tests/test_project_intelligence_pir11_generation_apply.py",),
    ),
    ProductionConsumerSpec(
        name="verification",
        phase="verification",
        path="agent/project_intelligence/verification_integration.py",
        markers=(
            "record_project_intelligence_verification",
            "project_intelligence.record_verification_result",
            "AtlasVerificationBridge",
        ),
        evidence_tests=("tests/test_project_intelligence_pir12_verification_recovery.py",),
    ),
    ProductionConsumerSpec(
        name="recovery",
        phase="recovery",
        path="agent/atlas_recovery_service.py",
        markers=(
            "_apply_project_intelligence_recovery",
            "project_intelligence_checkpoint",
            "project_intelligence_final_gate",
        ),
        evidence_tests=("tests/test_project_intelligence_pir12_verification_recovery.py",),
    ),
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _consumer_evidence(root: Path, spec: ProductionConsumerSpec) -> ProductionConsumerEvidence:
    path = root / spec.path
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = [marker for marker in spec.markers if marker not in text]
    return ProductionConsumerEvidence(
        name=spec.name,
        phase=spec.phase,
        path=spec.path,
        production_connected=not missing,
        missing_markers=missing,
        evidence_tests=list(spec.evidence_tests),
    )


def _phase_status(rollout_evidence: dict[str, Any], phase: str) -> dict[str, str]:
    for entry in rollout_evidence.get("entries", []):
        if entry.get("phase") == phase:
            return {
                "shadow_parity_status": str(entry.get("shadow_parity_status") or "not_recorded"),
                "rollback_status": str(entry.get("rollback_status") or "not_recorded"),
            }
    return {"shadow_parity_status": "not_recorded", "rollback_status": "not_recorded"}


def build_consumer_cutover_gate(
    root: str | Path,
    *,
    legacy_lint_report_path: str | Path | None = None,
    rollout_evidence_path: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    lint_report = _load_json(legacy_lint_report_path)
    rollout_evidence = _load_json(rollout_evidence_path)
    consumers = [_consumer_evidence(root_path, spec) for spec in REQUIRED_PRODUCTION_CONSUMERS]
    entries: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []
    lint_passed = bool(lint_report.get("passed")) if lint_report else False
    if not lint_passed:
        blocked_reasons.append("legacy_dependency_lint_not_passed")
    for consumer in consumers:
        phase_status = _phase_status(rollout_evidence, consumer.phase)
        ready = (
            consumer.production_connected
            and lint_passed
            and phase_status["shadow_parity_status"] == "passed"
            and phase_status["rollback_status"] == "passed"
        )
        reasons: list[str] = []
        if not consumer.production_connected:
            reasons.append("production_markers_missing")
        if phase_status["shadow_parity_status"] != "passed":
            reasons.append("shadow_parity_not_passed")
        if phase_status["rollback_status"] != "passed":
            reasons.append("rollback_drill_not_passed")
        if not lint_passed:
            reasons.append("legacy_dependency_lint_not_passed")
        blocked_reasons.extend(f"{consumer.name}:{reason}" for reason in reasons)
        entries.append(
            {
                **asdict(consumer),
                **phase_status,
                "cutover_ready": ready,
                "blocked_reasons": reasons,
            }
        )

    return {
        "schema_version": 1,
        "generated_at": generated_at or _utcnow_iso(),
        "source": "project_intelligence_consumer_cutover_gate",
        "repository_root": root_path.name,
        "entries": entries,
        "summary": {
            "required_consumer_count": len(consumers),
            "production_connected_count": sum(1 for consumer in consumers if consumer.production_connected),
            "cutover_ready_count": sum(1 for entry in entries if entry["cutover_ready"]),
            "legacy_dependency_lint_passed": lint_passed,
            "gate_passed": all(entry["cutover_ready"] for entry in entries),
            "blocked_reasons": sorted(set(blocked_reasons)),
        },
        "safety": {
            "advisory_only": True,
            "rollout_transition": False,
            "source_mutation": False,
            "legacy_retirement": False,
        },
    }


def write_consumer_cutover_gate(root: str | Path, output: str | Path, **kwargs: Any) -> dict[str, Any]:
    gate = build_consumer_cutover_gate(root, **kwargs)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return gate
