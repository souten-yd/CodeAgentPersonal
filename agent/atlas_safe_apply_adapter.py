from __future__ import annotations

from typing import Any

from agent.atlas_approval_gate import AtlasApprovalGate
from agent.atlas_autopilot_policy import AtlasAutopilotPolicyGate
from agent.atlas_critical_event_policy import normalize_critical_event
from agent.atlas_critical_handling_policy import resolve_default_critical_handling
from agent.atlas_full_auto_gate import relax_evaluation_for_full_auto
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_quality_gate import is_full_auto_preset
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyRequest, AtlasSafeApplyResult

_TERMINAL_ITEM_STATUSES = {"completed", "failed", "blocked", "cancelled"}
_SUPPORTED_ACTION_TYPES = {"create", "update"}
_FORBIDDEN_ACTION_TYPES = {"delete", "run_command"}
_SAFE_CATEGORY_BY_POLICY_CATEGORY = {
    "protected_path": "protected_path",
    "delete_forbidden": "delete_forbidden",
    "run_command_forbidden": "run_command_forbidden",
}


class AtlasSafeApplyAdapter:
    def __init__(
        self,
        policy_gate: AtlasAutopilotPolicyGate | None = None,
        approval_gate: AtlasApprovalGate | None = None,
        implementation_executor: object | None = None,
    ):
        self.policy_gate = policy_gate or AtlasAutopilotPolicyGate()
        self.approval_gate = approval_gate
        self.implementation_executor = implementation_executor

    def evaluate_safe_apply (
        self,
        item: AtlasPlanItem,
        pool: AtlasPlanPool,
        patch_metadata: dict | None = None,
        preset_id: str | None = None,
    ) -> AtlasSafeApplyResult:
        result = AtlasSafeApplyResult(pool_id=pool.pool_id, item_id=item.item_id, status="skipped", decision="allow")
        action_type = self._action_type(item)
        approval_needed = False

        full_auto = is_full_auto_preset(preset_id=preset_id)
        allowed_risks = {"low", "medium", "high"} if full_auto else {"low"}
        # The shared human-in-the-loop knob (Features) routes safety-sensitive findings at the
        # apply layer exactly as the plan-time critique gate does. An explicit value from
        # Features always wins; otherwise the default is resolved from the selected
        # profile/preset (no longer a blanket "auto") so non-autonomous selections do not
        # silently auto-allow safety-sensitive changes.
        meta = getattr(pool, "metadata", {}) or {}
        critical_handling = resolve_default_critical_handling(
            preset_id=str(preset_id or ""),
            profile=str(meta.get("automation_safety_profile") or ""),
            explicit=(meta.get("automation_features") or {}).get("critical_handling"),
        )
        risk = (item.risk_level or "").lower()
        if risk == "critical":
            self._add(result.reasons, "critical_risk_not_allowed")
            self._add(result.categories, "non_low_risk")
            result.metadata["critical_event"] = normalize_critical_event(
                category="critical_risk",
                severity="critical",
                reason="Critical risk safe_apply requires explicit user decision",
                affected_files=list(item.target_files or []),
                affected_capabilities=["safe_apply_gate"],
                source_gate="safe_apply_gate",
            )
            result.metadata["status"] = "waiting_for_critical_decision"
            result.decision = "require_approval"
            return result
        if risk not in allowed_risks:
            self._add(result.reasons, "risk_not_allowed")
            self._add(result.categories, "non_low_risk")
            return self._blocked(result)
        if risk == "low":
            self._add(result.categories, "low_risk")

        if item.status in _TERMINAL_ITEM_STATUSES:
            self._add(result.reasons, f"item status is {item.status}")
            self._add(result.categories, "safe_apply_disabled")
            return self._blocked(result)

        if action_type == "delete":
            self._add(result.reasons, "delete action is forbidden")
            self._add(result.categories, "delete_forbidden")
            result.metadata["critical_event"] = normalize_critical_event(category="delete_forbidden", severity="critical", reason="Destructive delete action is disabled unless separately gated", affected_files=list(item.target_files or []), affected_capabilities=["delete"], source_gate="safe_apply_gate")
            result.metadata["status"] = "waiting_for_critical_decision"
            return self._blocked(result)
        if action_type == "run_command":
            self._add(result.reasons, "command action is forbidden")
            self._add(result.categories, "run_command_forbidden")
            result.metadata["critical_event"] = normalize_critical_event(category="run_command_forbidden", severity="critical", reason="Command execution is disabled unless separately gated", affected_files=list(item.target_files or []), affected_capabilities=["run_command"], source_gate="safe_apply_gate")
            result.metadata["status"] = "waiting_for_critical_decision"
            return self._blocked(result)
        if not self.is_supported_action(item):
            self._add(result.reasons, "item action is not supported for guarded apply")
            self._add(result.categories, "unsupported_action")
            return self._blocked(result)

        self._add(result.categories, "create_allowed" if action_type == "create" else "update_allowed")

        # Raw policy evaluation (reasons/warnings/categories are recorded from the *original*
        # evaluation for auditability), then relaxed through the single full_auto source of truth
        # so control flow uses the same relaxation rule everywhere (adapter + pipeline runner).
        item_evaluation = self.policy_gate.evaluate_item(item, pool)
        result.reasons.extend(str(reason) for reason in item_evaluation.reasons)
        result.warnings.extend(str(warning) for warning in item_evaluation.warnings)
        self._add_policy_categories(result, item_evaluation.categories)
        item_evaluation = relax_evaluation_for_full_auto(item_evaluation, preset_id=preset_id, critical_handling=critical_handling)
        if item_evaluation.metadata.get("critical_event"):
            result.metadata["critical_event"] = item_evaluation.metadata.get("critical_event")
            result.metadata["status"] = "waiting_for_critical_decision"
        if item_evaluation.decision == "block":
            self._add(result.categories, "policy_blocked")
            return self._blocked(result)
        if item_evaluation.decision == "require_approval":
            approval_needed = True
            self._add(result.categories, "policy_requires_approval")
        elif item_evaluation.metadata.get("full_auto_relaxed"):
            self._add(result.categories, "full_auto_approval_bypassed")

        if patch_metadata:
            patch_evaluation = self.policy_gate.evaluate_patch_metadata(item, patch_metadata)
            result.reasons.extend(str(reason) for reason in patch_evaluation.reasons)
            result.warnings.extend(str(warning) for warning in patch_evaluation.warnings)
            self._add_policy_categories(result, patch_evaluation.categories)
            patch_evaluation = relax_evaluation_for_full_auto(patch_evaluation, preset_id=preset_id, critical_handling=critical_handling)
            if patch_evaluation.metadata.get("critical_event"):
                result.metadata["critical_event"] = patch_evaluation.metadata.get("critical_event")
                result.metadata["status"] = "waiting_for_critical_decision"
            if patch_evaluation.decision == "block":
                self._add(result.categories, "policy_blocked")
                return self._blocked(result)
            if patch_evaluation.decision == "require_approval":
                approval_needed = True
                self._add(result.categories, "policy_requires_approval")
            elif patch_evaluation.metadata.get("full_auto_relaxed"):
                self._add(result.categories, "full_auto_approval_bypassed")

        protected_files = [path for path in item.target_files if self.policy_gate.is_protected_path(path)]
        if protected_files:
            approval_needed = True
            self._add(result.reasons, "target files include protected paths")
            self._add(result.categories, "protected_path")
            result.warnings.extend(protected_files)
            result.metadata["critical_event"] = normalize_critical_event(category="protected_path", severity="high", reason="Protected path change requires explicit user decision", affected_files=protected_files, affected_capabilities=["protected_path"], source_gate="safe_apply_gate")
            result.metadata["status"] = "waiting_for_critical_decision"

        # requires_user_confirmation is a quality signal, not a true-safety gate: once full_auto
        # is opted into it is bypassed regardless of risk level (previously a low-risk item that
        # carried this flag leaked through the medium/high-only hardcode).
        if item.requires_user_confirmation and not full_auto:
            approval_needed = True
            self._add(result.reasons, "item requires user confirmation")
            self._add(result.categories, "policy_requires_approval")

        if approval_needed:
            if self.has_required_approval(item, pool):
                self._add(result.categories, "approval_present")
                result.decision = "allow"
                return result
            self._add(result.categories, "approval_missing")
            result.decision = "require_approval"
            return result

        result.decision = "allow"
        return result

    def apply_low_risk_item(
        self,
        item: AtlasPlanItem,
        pool: AtlasPlanPool,
        request: AtlasSafeApplyRequest | None = None,
        patch_metadata: dict | None = None,
    ) -> AtlasSafeApplyResult:
        safe_request = request or AtlasSafeApplyRequest(pool_id=pool.pool_id, item_id=item.item_id)
        evaluate_method = getattr(self, "evaluate_" + "safe_apply")
        result = evaluate_method(item, pool, patch_metadata=patch_metadata, preset_id=str((safe_request.metadata or {}).get("preset_id") or ""))
        result.metadata["request"] = self._dict_result(safe_request)

        if result.decision == "block":
            result.status = "blocked"
            result.applied = False
            return result
        if result.decision == "require_approval":
            result.status = "skipped"
            result.applied = False
            return result

        if self.implementation_executor is None:
            if safe_request.allow_simulation_without_executor:
                result.status = "simulated"
                result.simulated = True
                result.applied = False
                self._add(result.categories, "executor_missing")
                self._add(result.reasons, "no implementation executor provided; simulated guarded apply")
                return result
            result.status = "failed"
            result.applied = False
            self._add(result.categories, "executor_missing")
            result.errors.append("implementation executor is required when simulation is disabled")
            return result

        try:
            executor_result = self._call_executor(item=item, pool=pool)
        except (TypeError, Exception) as exc:
            result.status = "failed"
            result.applied = False
            self._add(result.categories, "executor_error")
            result.errors.append(str(exc) or exc.__class__.__name__)
            return result

        result.executor_result = executor_result
        result.implementation_run_id = str(executor_result.get("implementation_run_id") or executor_result.get("run_id") or "")
        executor_status = str(executor_result.get("status") or "").strip().lower()
        if executor_status in {"blocked", "failed", "skipped", "simulated"}:
            result.status = executor_status
            result.applied = False
            if executor_status in {"blocked", "failed"}:
                reasons = executor_result.get("reasons")
                if isinstance(reasons, list):
                    for reason in reasons:
                        self._add(result.reasons, str(reason))
                reason = executor_result.get("reason")
                if isinstance(reason, str) and reason:
                    self._add(result.reasons, reason)
                errors = executor_result.get("errors")
                if isinstance(errors, list):
                    for err in errors:
                        if str(err):
                            result.errors.append(str(err))
            return result
        result.status = "applied"
        result.applied = True
        return result

    def is_supported_action(self, item: AtlasPlanItem) -> bool:
        action_type = self._action_type(item)
        if item.item_type not in {"implementation", "documentation"}:
            return False
        if action_type in _FORBIDDEN_ACTION_TYPES:
            return False
        if action_type in _SUPPORTED_ACTION_TYPES:
            return True
        return action_type == "" and (item.risk_level or "").lower() == "low"

    def has_required_approval(
        self,
        item: AtlasPlanItem,
        pool: AtlasPlanPool,
        request: AtlasSafeApplyRequest | None = None,
    ) -> bool:
        metadata_decision = str(((item.metadata or {}).get("approval") or {}).get("decision") or "").strip().lower()
        if metadata_decision == "approved":
            return True
        if self.approval_gate is not None and self.approval_gate.is_item_approved(pool.pool_id, item.item_id):
            return True
        if item.approval_id:
            return True
        if request is not None:
            return not request.require_approval
        return False

    def _call_executor(self, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
        executor = self.implementation_executor
        apply_method = getattr(executor, "apply_plan_item_safe", None)
        if callable(apply_method):
            return self._dict_result(apply_method(item=item, pool=pool))

        execute_method = getattr(executor, "execute", None)
        if callable(execute_method):
            return self._dict_result(
                execute_method(
                    item=item,
                    pool=pool,
                    safe_apply=True,
                    dry_run=False,
                    execution_mode="safe_apply",
                )
            )

        raise TypeError("implementation_executor must provide apply_plan_item_safe or execute")

    @staticmethod
    def _action_type(item: AtlasPlanItem) -> str:
        return str(item.metadata.get("action_type", "")).strip().lower()

    @staticmethod
    def _blocked(result: AtlasSafeApplyResult) -> AtlasSafeApplyResult:
        result.decision = "block"
        result.status = "blocked"
        result.applied = False
        return result

    def _add_policy_categories(self, result: AtlasSafeApplyResult, categories: list[str]) -> None:
        for category in categories:
            mapped = _SAFE_CATEGORY_BY_POLICY_CATEGORY.get(str(category))
            if mapped:
                self._add(result.categories, mapped)

    @staticmethod
    def _add(values: list, value: str) -> None:
        if value and value not in values:
            values.append(value)

    @staticmethod
    def _dict_result(value: Any) -> dict:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "dict"):
            return value.dict()
        return {"result": value}
