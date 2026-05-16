from __future__ import annotations

from uuid import uuid4

from agent.atlas_autopilot_policy_schema import (
    AtlasAutopilotPolicy,
    AtlasPolicyEvaluation,
    AtlasPolicyReasonCategory,
)
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


_BLOCKED_ITEM_STATUSES = {"failed", "blocked", "cancelled"}


class AtlasAutopilotPolicyGate:
    def __init__(self, policy: AtlasAutopilotPolicy | None = None):
        self.policy = policy or AtlasAutopilotPolicy()

    def evaluate_item(self, item: AtlasPlanItem, pool: AtlasPlanPool | None = None) -> AtlasPolicyEvaluation:
        reasons: list[str] = []
        warnings: list[str] = []
        categories: list[AtlasPolicyReasonCategory] = []
        requires_approval = False
        blocked = False
        risk_level = (item.risk_level or "medium").lower()
        action_type = str(item.metadata.get("action_type", "")).strip().lower()

        if item.status in _BLOCKED_ITEM_STATUSES:
            blocked = True
            reasons.append(f"item status is {item.status}")
            categories.append("manual_gate")

        if risk_level == "critical":
            blocked = True
            reasons.append("critical risk item is blocked by default")
            categories.append("critical_risk")
        elif risk_level == "high":
            requires_approval = True
            reasons.append("high risk item requires approval")
            categories.append("high_risk")
        elif risk_level == "low":
            categories.append("low_risk")
        elif risk_level in self.policy.manual_gate_risks:
            requires_approval = True
            reasons.append(f"{risk_level} risk item requires approval")
            categories.append("manual_gate")
        elif risk_level not in {"low", "medium", "high", "critical"}:
            requires_approval = True
            reasons.append(f"unknown risk level: {risk_level}")
            categories.append("unknown_risk")

        if item.requires_user_confirmation:
            requires_approval = True
            reasons.append("item requires user confirmation")
            categories.append("manual_gate")

        protected_files = [path for path in item.target_files if self.is_protected_path(path)]
        if protected_files:
            requires_approval = True
            reasons.append("target files include protected paths")
            categories.append("protected_path")
            warnings.extend(protected_files)

        if len(item.target_files) > self.policy.max_changed_files_per_item:
            requires_approval = True
            reasons.append("target file count exceeds policy limit")
            categories.append("too_many_files")

        if action_type == "delete" and not self.policy.allow_delete:
            blocked = True
            reasons.append("delete action is forbidden by policy")
            categories.append("delete_forbidden")

        if action_type == "run_command" and not self.policy.allow_run_command:
            blocked = True
            reasons.append("command action is forbidden by policy")
            categories.append("run_command_forbidden")

        if item.item_type == "verification" and item.test_commands:
            if not self.policy.allow_test_command:
                blocked = True
                reasons.append("test commands are forbidden by policy")
                categories.append("run_command_forbidden")
            else:
                forbidden_commands = [command for command in item.test_commands if not self.is_allowed_test_command(command)]
                if forbidden_commands:
                    blocked = True
                    reasons.append("verification item contains commands outside the allowlist")
                    categories.append("run_command_forbidden")
                    warnings.extend(forbidden_commands)

        if blocked:
            decision = "block"
            auto_execution_allowed = False
        elif risk_level == "low" and not item.requires_user_confirmation and not requires_approval:
            decision = "allow"
            auto_execution_allowed = self.policy.auto_execute_low_risk
        else:
            decision = "require_approval"
            auto_execution_allowed = False
            if "manual_gate" not in categories and risk_level in {"medium", "unknown"}:
                categories.append("manual_gate")
            if not reasons:
                reasons.append("manual policy gate required")

        return AtlasPolicyEvaluation(
            evaluation_id=self._evaluation_id("item"),
            scope="item",
            decision=decision,
            item_id=item.item_id,
            pool_id=pool.pool_id if pool is not None else item.pool_id,
            risk_level=risk_level,
            reasons=self._dedupe(reasons),
            categories=self._dedupe(categories),
            requires_user_confirmation=decision == "require_approval",
            auto_execution_allowed=auto_execution_allowed,
            blocked=decision == "block",
            warnings=self._dedupe(warnings),
            metadata={"status": item.status, "action_type": action_type, "target_files_count": len(item.target_files)},
        )

    def evaluate_pool(self, pool: AtlasPlanPool) -> AtlasPolicyEvaluation:
        reasons: list[str] = []
        categories: list[AtlasPolicyReasonCategory] = []

        item_evaluations = [self.evaluate_item(item, pool=pool) for item in pool.items]
        blocked_item_ids = [evaluation.item_id for evaluation in item_evaluations if evaluation.decision == "block"]
        approval_required_item_ids = [
            evaluation.item_id for evaluation in item_evaluations if evaluation.decision == "require_approval"
        ]
        allowed_item_ids = [evaluation.item_id for evaluation in item_evaluations if evaluation.decision == "allow"]

        if not pool.items:
            reasons.append("pool has no plan items")
            categories.append("manual_gate")

        if len(pool.items) > self.policy.max_items_per_run:
            reasons.append("pool item count exceeds policy limit")
            categories.append("too_many_files")
            approval_required_item_ids.extend(item.item_id for item in pool.items if item.item_id not in approval_required_item_ids)

        if pool.metadata.get("destructive_change_detected"):
            reasons.append("pool metadata reports destructive change")
            categories.append("destructive_change")
            approval_required_item_ids.extend(item.item_id for item in pool.items if item.item_id not in approval_required_item_ids)

        if pool.metadata.get("requires_user_confirmation"):
            reasons.append("pool metadata requires user confirmation")
            categories.append("manual_gate")
            approval_required_item_ids.extend(item.item_id for item in pool.items if item.item_id not in approval_required_item_ids)

        for evaluation in item_evaluations:
            categories.extend(evaluation.categories)

        if blocked_item_ids:
            decision = "block"
        elif approval_required_item_ids or reasons or not pool.items:
            decision = "require_approval"
        else:
            decision = "allow"

        return AtlasPolicyEvaluation(
            evaluation_id=self._evaluation_id("pool"),
            scope="pool",
            decision=decision,
            pool_id=pool.pool_id,
            risk_level="medium",
            reasons=self._dedupe(reasons),
            categories=self._dedupe(categories),
            requires_user_confirmation=decision == "require_approval",
            auto_execution_allowed=decision == "allow",
            blocked=decision == "block",
            metadata={
                "item_evaluations_count": len(item_evaluations),
                "blocked_item_ids": self._dedupe(blocked_item_ids),
                "approval_required_item_ids": self._dedupe(approval_required_item_ids),
                "allowed_item_ids": self._dedupe(allowed_item_ids),
            },
        )

    def evaluate_patch_metadata(self, item: AtlasPlanItem, patch_metadata: dict) -> AtlasPolicyEvaluation:
        reasons: list[str] = []
        warnings: list[str] = []
        categories: list[AtlasPolicyReasonCategory] = []
        requires_approval = False
        blocked = False
        risk_level = (item.risk_level or "medium").lower()
        changed_files = list(patch_metadata.get("changed_files") or [])
        patch_bytes = int(patch_metadata.get("patch_bytes") or 0)
        action_type = str(patch_metadata.get("action_type") or item.metadata.get("action_type", "")).strip().lower()

        if risk_level == "critical":
            blocked = True
            reasons.append("critical risk patch is blocked by default")
            categories.append("critical_risk")
        elif risk_level == "high":
            requires_approval = True
            reasons.append("high risk patch requires approval")
            categories.append("high_risk")

        if patch_metadata.get("destructive_change_detected"):
            requires_approval = True
            reasons.append("patch metadata reports destructive change")
            categories.append("destructive_change")
        if patch_metadata.get("dependency_change"):
            requires_approval = True
            reasons.append("patch metadata reports dependency change")
            categories.append("dependency_change")
        if patch_metadata.get("data_loss"):
            blocked = True
            reasons.append("patch metadata reports data loss risk")
            categories.append("data_loss")
        if patch_metadata.get("api_breaking_change"):
            requires_approval = True
            reasons.append("patch metadata reports API breaking change")
            categories.append("api_breaking_change")
        if patch_metadata.get("ui_breaking_change"):
            requires_approval = True
            reasons.append("patch metadata reports UI breaking change")
            categories.append("ui_breaking_change")
        if patch_metadata.get("security"):
            requires_approval = True
            reasons.append("patch metadata reports security risk")
            categories.append("security")
        if patch_metadata.get("docker_change"):
            requires_approval = True
            reasons.append("patch metadata reports Docker change")
            categories.append("docker_change")
        if patch_metadata.get("database_migration"):
            requires_approval = True
            reasons.append("patch metadata reports database migration")
            categories.append("database_migration")

        if patch_bytes > self.policy.max_patch_bytes:
            requires_approval = True
            reasons.append("patch size exceeds policy limit")
            categories.append("patch_too_large")

        if len(changed_files) > self.policy.max_changed_files_per_item:
            requires_approval = True
            reasons.append("changed file count exceeds policy limit")
            categories.append("too_many_files")

        protected_files = [path for path in changed_files if self.is_protected_path(path)]
        if protected_files:
            requires_approval = True
            reasons.append("patch changes protected paths")
            categories.append("protected_path")
            warnings.extend(protected_files)

        if action_type == "delete" and not self.policy.allow_delete:
            blocked = True
            reasons.append("delete action is forbidden by policy")
            categories.append("delete_forbidden")

        if action_type == "run_command" and not self.policy.allow_run_command:
            blocked = True
            reasons.append("command action is forbidden by policy")
            categories.append("run_command_forbidden")

        if blocked:
            decision = "block"
            auto_execution_allowed = False
        elif requires_approval:
            decision = "require_approval"
            auto_execution_allowed = False
        elif risk_level == "low":
            decision = "allow"
            auto_execution_allowed = self.policy.auto_apply_low_risk_patches
            categories.append("low_risk")
        else:
            decision = "require_approval"
            auto_execution_allowed = False
            categories.append("manual_gate")
            reasons.append("patch metadata requires manual policy gate")

        return AtlasPolicyEvaluation(
            evaluation_id=self._evaluation_id("patch"),
            scope="patch",
            decision=decision,
            item_id=item.item_id,
            pool_id=item.pool_id,
            risk_level=risk_level,
            reasons=self._dedupe(reasons),
            categories=self._dedupe(categories),
            requires_user_confirmation=decision == "require_approval",
            auto_execution_allowed=auto_execution_allowed,
            blocked=decision == "block",
            warnings=self._dedupe(warnings),
            metadata={
                "changed_files_count": len(changed_files),
                "patch_bytes": patch_bytes,
                "action_type": action_type,
            },
        )

    def is_protected_path(self, path: str) -> bool:
        normalized = self._normalize_path(path)
        if not normalized:
            return False
        for protected_path in self.policy.protected_paths:
            protected = self._normalize_path(protected_path)
            if normalized == protected or normalized.startswith(f"{protected}/"):
                return True
        return False

    def is_allowed_test_command(self, command: str) -> bool:
        normalized = command.strip()
        if not normalized:
            return False
        return any(normalized.startswith(allowed.strip()) for allowed in self.policy.allowed_test_commands if allowed.strip())

    def _evaluation_id(self, scope: str) -> str:
        return f"atlas_policy_{scope}_{uuid4().hex}"

    def _normalize_path(self, path: str) -> str:
        return str(path or "").replace("\\", "/").strip().strip("/")

    def _dedupe(self, values: list):
        deduped = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        return deduped
