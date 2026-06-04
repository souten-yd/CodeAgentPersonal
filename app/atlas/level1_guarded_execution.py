from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Level1DisabledReason:
    gate: str
    blocker: str


@dataclass(frozen=True)
class Level1ExecutionRequestMetadata:
    enabled: bool
    runtime_level: str
    level1_execution_enabled: bool
    backend_skeleton_enabled: bool
    callable_execution_endpoint_enabled: bool
    vue_execution_controls_enabled: bool
    dry_run_required: bool
    explicit_approval_required: bool
    single_action_only_required: bool


@dataclass(frozen=True)
class Level1ExecutionReadinessResult:
    metadata: Level1ExecutionRequestMetadata
    required_gates: list[str]
    blockers: list[Level1DisabledReason]


def build_level1_gate_source_map() -> list[dict[str, object]]:
    gates = [
        ("snapshot_restore", "Snapshot / Restore", "backend", "snapshot_manifest", "Snapshot manifest with restorable file set evidence."),
        ("patch_transaction", "Patch Transaction", "backend", "patch_transaction_log", "Patch transaction metadata and rollback transaction references."),
        ("risk_classification", "Risk Classification", "backend", "risk_profile", "Risk class evidence for planned operation."),
        ("dry_run_proof", "Dry-run Proof", "backend", "dry_run_report", "Dry-run result artifact proving pre-execution simulation."),
        ("explicit_approval_token", "Explicit Approval Token", "operator", "approval_token", "Operator-provided approval token evidence."),
        ("allowlisted_verification", "Allowlisted Verification", "backend", "verification_allowlist", "Allowlisted verification command evidence only."),
        ("rollback_readiness", "Rollback Readiness", "backend", "rollback_manifest", "Rollback restore plan and manifest references."),
        ("artifact_capture", "Artifact Capture", "backend", "artifact_manifest", "Artifacts for plan/dry-run/result capture references."),
        ("stop_kill_switch", "Stop / Kill Switch", "backend", "stop_gate_state", "Stop-gate presence and explicit no-auto-continue evidence."),
        ("loop_bounds", "Loop Bounds", "backend", "loop_bound_policy", "Bounded retries/runtime/actions evidence."),
        ("remote_git_restriction", "Remote Git Restriction", "backend", "remote_git_policy", "Remote-git restriction evidence with requested_operation=none."),
        ("self_improvement_gate", "Self-improvement Gate", "backend", "self_improvement_policy", "Self-modification gate evidence remains metadata-only."),
        ("audit_log", "Audit Log", "backend", "audit_log_reference", "Audit trail reference for readiness reporting."),
        ("data_root_path_safety", "Data-root Path Safety", "backend", "path_safety_contract", "Resolved data_root and path-safety evidence."),
        ("forbidden_command_execution_policy", "Forbidden Command Execution Policy", "backend", "command_policy", "Forbidden command classes policy evidence."),
        ("backend_authority_enforcement", "Backend Authority Enforcement", "backend", "workflow_state_contract", "Backend workflow_state remains authoritative."),
        ("ui_non_authority_enforcement", "UI Non-authority Enforcement", "frontend", "ui_contract", "UI remains non-authoritative and non-executing."),
    ]
    return [
        {
            "gate_id": gate_id,
            "label": label,
            "owner": owner,
            "source": source,
            "evidence_required": evidence_required,
            "evidence_available": False,
            "current_status": "missing_evidence",
            "blocker_reason": "Evidence has not been generated for this read-only checkpoint.",
            "test_requirement": f"Contract test coverage required for {gate_id} metadata gate mapping.",
            "execution_relevance": "Read-only checkpoint gate evidence for backend-supervised automation.",
            "mutable": False,
            "advisory_only": True,
        }
        for gate_id, label, owner, source, evidence_required in gates
    ]


_POLICY_ENFORCED_GATES = {
    "remote_git_restriction",
    "data_root_path_safety",
    "forbidden_command_execution_policy",
    "backend_authority_enforcement",
    "ui_non_authority_enforcement",
    "audit_log",
}

_ARTIFACT_KEYS_BY_GATE = {
    "snapshot_restore": ("snapshot",),
    "patch_transaction": ("transaction",),
    "risk_classification": ("risk",),
    "dry_run_proof": ("dry_run",),
    "allowlisted_verification": ("allowlist",),
    "rollback_readiness": ("rollback",),
    "artifact_capture": ("artifact_capture",),
    "stop_kill_switch": ("stop",),
    "self_improvement_gate": ("self_improvement",),
}


def build_level1_gate_source_map_with_evidence(
    *,
    artifacts: dict[str, Any] | None = None,
    profile_resolution: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    artifacts_payload = artifacts if isinstance(artifacts, dict) else {}
    profile_payload = profile_resolution if isinstance(profile_resolution, dict) else {}
    manifest_payload = manifest if isinstance(manifest, dict) else {}
    checkpoint = str(
        manifest_payload.get("current_automation_track")
        or manifest_payload.get("next_level_advancement_pr")
        or "backend-supervised-automation-checkpoint"
    )
    gate_source_map = build_level1_gate_source_map()
    for gate in gate_source_map:
        gate_id = str(gate.get("gate_id") or "")
        evidence_available = _gate_has_evidence(gate_id, artifacts_payload, profile_payload)
        if gate_id in _POLICY_ENFORCED_GATES:
            gate["evidence_available"] = True
            gate["current_status"] = "policy_enforced"
            gate["blocker_reason"] = ""
        elif evidence_available:
            gate["evidence_available"] = True
            gate["current_status"] = "satisfied"
            gate["blocker_reason"] = ""
        else:
            gate["evidence_available"] = False
            gate["current_status"] = "missing_evidence"
            gate["blocker_reason"] = f"Missing evidence for {gate_id} in {checkpoint}."
        gate["execution_relevance"] = f"Read-only evidence for {checkpoint}; this report does not execute actions."
    return gate_source_map


def _gate_has_evidence(gate_id: str, artifacts: dict[str, Any], profile_resolution: dict[str, Any]) -> bool:
    if gate_id == "explicit_approval_token":
        metadata = artifacts.get("metadata") if isinstance(artifacts.get("metadata"), dict) else {}
        return bool(
            artifacts.get("approval_token")
            or artifacts.get("explicit_approval_token")
            or metadata.get("approval_token")
            or metadata.get("explicit_approval_token")
        )
    if gate_id == "loop_bounds":
        return bool(
            artifacts.get("loop_bound")
            or _positive_int(profile_resolution.get("max_actions"))
            or _positive_int(profile_resolution.get("max_retries"))
            or _positive_int(profile_resolution.get("max_changed_files"))
            or _positive_int(profile_resolution.get("max_runtime_seconds"))
        )
    if gate_id == "self_improvement_gate" and bool(profile_resolution.get("self_improvement")):
        return True
    return any(bool(artifacts.get(key)) for key in _ARTIFACT_KEYS_BY_GATE.get(gate_id, ()))


def _positive_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


class Level1GuardedExecutionSkeleton:
    """Disabled metadata-only skeleton for future Level-1 guarded single-step execution."""

    @staticmethod
    def describe_disabled_level1_readiness() -> Level1ExecutionReadinessResult:
        return build_level1_disabled_readiness_result()

    @staticmethod
    def build_disabled_level1_contract() -> dict[str, object]:
        return Level1GuardedExecutionSkeleton.build_level1_contract(_zero_evidence_default=True)

    @staticmethod
    def build_level1_contract(
        *,
        artifacts: dict[str, Any] | None = None,
        profile_resolution: dict[str, Any] | None = None,
        manifest: dict[str, Any] | None = None,
        _zero_evidence_default: bool = False,
    ) -> dict[str, object]:
        result = build_level1_readiness_result(profile_resolution=profile_resolution, manifest=manifest)
        gate_source_map = (
            build_level1_gate_source_map()
            if _zero_evidence_default
            else build_level1_gate_source_map_with_evidence(
                artifacts=artifacts,
                profile_resolution=profile_resolution,
                manifest=manifest,
            )
        )
        missing_evidence_count = sum(1 for gate in gate_source_map if not gate["evidence_available"])
        satisfied_gate_count = len(gate_source_map) - missing_evidence_count
        unsatisfied_gate_count = missing_evidence_count
        blockers = [
            Level1DisabledReason(gate=str(gate["gate_id"]), blocker=str(gate["blocker_reason"]))
            for gate in gate_source_map
            if str(gate.get("current_status")) == "missing_evidence" and str(gate.get("blocker_reason"))
        ]
        return {
            "enabled": result.metadata.enabled,
            "runtime_level": result.metadata.runtime_level,
            "level1_execution_enabled": result.metadata.level1_execution_enabled,
            "backend_skeleton_enabled": result.metadata.backend_skeleton_enabled,
            "callable_execution_endpoint_enabled": result.metadata.callable_execution_endpoint_enabled,
            "vue_execution_controls_enabled": result.metadata.vue_execution_controls_enabled,
            "dry_run_required": result.metadata.dry_run_required,
            "explicit_approval_required": result.metadata.explicit_approval_required,
            "single_action_only_required": result.metadata.single_action_only_required,
            "required_gates": result.required_gates,
            "blockers": [asdict(item) for item in blockers],
            "gate_source_map": gate_source_map,
            "evidence_summary": {
                "required_gate_count": len(gate_source_map),
                "missing_evidence_count": missing_evidence_count,
                "satisfied_gate_count": satisfied_gate_count,
                "unsatisfied_gate_count": unsatisfied_gate_count,
                "all_gates_advisory_only": True,
                "all_gates_mutable": False,
            },
            "missing_evidence_count": missing_evidence_count,
            "satisfied_gate_count": satisfied_gate_count,
            "unsatisfied_gate_count": unsatisfied_gate_count,
            "advisory_only": True,
            "mutation_performed": False,
            "execution_performed": False,
        }


def build_level1_disabled_readiness_result() -> Level1ExecutionReadinessResult:
    return build_level1_readiness_result(profile_resolution=None, manifest=None)


def build_level1_readiness_result(
    *,
    profile_resolution: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> Level1ExecutionReadinessResult:
    required_gates = [
        "snapshot_restore",
        "patch_transaction",
        "risk_classification",
        "dry_run_proof",
        "explicit_approval_token",
        "allowlisted_verification",
        "rollback_readiness",
        "artifact_capture",
        "stop_kill_switch",
        "loop_bounds",
        "remote_git_restriction",
        "self_improvement_gate",
        "audit_log",
        "data_root_path_safety",
        "forbidden_command_execution_policy",
        "backend_authority_enforcement",
        "ui_non_authority_enforcement",
    ]
    profile_payload = profile_resolution if isinstance(profile_resolution, dict) else {}
    manifest_payload = manifest if isinstance(manifest, dict) else {}
    runtime_level = str(
        profile_payload.get("runtime_level")
        or manifest_payload.get("default_runtime_level")
        or "level_0_review_only"
    )
    profile = str(profile_payload.get("profile") or "review_only")
    manifest_level1_enabled = bool(manifest_payload.get("level1_execution_enabled", False))
    level1_execution_enabled = bool(manifest_level1_enabled and profile != "review_only")
    blockers = [
        Level1DisabledReason(gate=gate, blocker="Evidence has not been generated for this read-only checkpoint.")
        for gate in required_gates
    ]
    metadata = Level1ExecutionRequestMetadata(
        enabled=level1_execution_enabled,
        runtime_level=runtime_level,
        level1_execution_enabled=level1_execution_enabled,
        backend_skeleton_enabled=True,
        callable_execution_endpoint_enabled=False,
        vue_execution_controls_enabled=False,
        dry_run_required=True,
        explicit_approval_required=True,
        single_action_only_required=True,
    )
    return Level1ExecutionReadinessResult(metadata=metadata, required_gates=required_gates, blockers=blockers)
