from __future__ import annotations

from dataclasses import asdict, dataclass


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
            "blocker_reason": "Level-1 execution remains disabled; metadata checkpoint only.",
            "test_requirement": f"Contract test coverage required for {gate_id} metadata gate mapping.",
            "execution_relevance": "Future Level-1 guarded execution gate; not callable in SCALE-96.",
            "mutable": False,
            "advisory_only": True,
        }
        for gate_id, label, owner, source, evidence_required in gates
    ]


class Level1GuardedExecutionSkeleton:
    """Disabled metadata-only skeleton for future Level-1 guarded single-step execution."""

    @staticmethod
    def describe_disabled_level1_readiness() -> Level1ExecutionReadinessResult:
        return build_level1_disabled_readiness_result()

    @staticmethod
    def build_disabled_level1_contract() -> dict[str, object]:
        result = build_level1_disabled_readiness_result()
        gate_source_map = build_level1_gate_source_map()
        missing_evidence_count = sum(1 for gate in gate_source_map if not gate["evidence_available"])
        satisfied_gate_count = len(gate_source_map) - missing_evidence_count
        unsatisfied_gate_count = missing_evidence_count
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
            "blockers": [asdict(item) for item in result.blockers],
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
    required_gates = [
        "snapshot_restore",
        "patch_transaction",
        "risk_classification",
        "verification_allowlist",
        "dry_run_approval",
        "rollback_readiness",
        "artifact_capture",
        "stop_kill_switch",
        "loop_bound",
        "remote_git_restrictions",
        "self_improvement",
    ]
    blockers = [
        Level1DisabledReason(gate=gate, blocker="Disabled in SCALE-94 metadata-only backend skeleton; not callable.")
        for gate in required_gates
    ]
    metadata = Level1ExecutionRequestMetadata(
        enabled=False,
        runtime_level="level_0_manual_only",
        level1_execution_enabled=False,
        backend_skeleton_enabled=True,
        callable_execution_endpoint_enabled=False,
        vue_execution_controls_enabled=False,
        dry_run_required=True,
        explicit_approval_required=True,
        single_action_only_required=True,
    )
    return Level1ExecutionReadinessResult(metadata=metadata, required_gates=required_gates, blockers=blockers)
