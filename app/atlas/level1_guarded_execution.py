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


class Level1GuardedExecutionSkeleton:
    """Disabled metadata-only skeleton for future Level-1 guarded single-step execution."""

    @staticmethod
    def describe_disabled_level1_readiness() -> Level1ExecutionReadinessResult:
        return build_level1_disabled_readiness_result()

    @staticmethod
    def build_disabled_level1_contract() -> dict[str, object]:
        result = build_level1_disabled_readiness_result()
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
