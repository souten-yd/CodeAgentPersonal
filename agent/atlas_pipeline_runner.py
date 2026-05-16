from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.atlas_autopilot_policy import AtlasAutopilotPolicyGate
from agent.atlas_approval_gate import AtlasApprovalGate
from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation
from agent.atlas_pipeline_runner_schema import (
    AtlasPipelineItemResult,
    AtlasPipelineRunRequest,
    AtlasPipelineRunState,
    _utc_now_iso,
)
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_safe_apply_adapter import AtlasSafeApplyAdapter
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyRequest, AtlasSafeApplyResult
from agent.test_command_runner import TestCommandRunner
from agent.test_command_runner_schema import AtlasTestCommandBatchResult


class AtlasPipelineRunner:
    def __init__(
        self,
        storage: AtlasPlanPoolStorage,
        policy_gate: AtlasAutopilotPolicyGate | None = None,
        implementation_executor: object | None = None,
        approval_gate: AtlasApprovalGate | None = None,
        safe_apply_adapter: AtlasSafeApplyAdapter | None = None,
        test_command_runner: TestCommandRunner | None = None,
    ):
        self.storage = storage
        self.policy_gate = policy_gate or AtlasAutopilotPolicyGate()
        self.implementation_executor = implementation_executor
        self.approval_gate = approval_gate
        self.safe_apply_adapter = safe_apply_adapter
        self.test_command_runner = test_command_runner

    def run_dry_run(self, request: AtlasPipelineRunRequest) -> AtlasPipelineRunState:
        if not request.dry_run:
            raise ValueError("AtlasPipelineRunner only supports dry_run=True in this PR")

        pool = self.storage.load_pool(request.pool_id)
        state = AtlasPipelineRunState(
            run_id=request.run_id or f"atlas_pipeline_run_{uuid4().hex}",
            pool_id=pool.pool_id,
            metadata={"request": self._request_metadata(request)},
        )
        state.add_event("pipeline_created", message="Pipeline dry-run state created.")
        state.status = "running"
        state.add_event("pipeline_started", message="Pipeline dry-run started.")

        pool.status = "running"
        pool.updated_at = _utc_now_iso()

        pool_evaluation = self.policy_gate.evaluate_pool(pool)
        state.metadata["pool_policy"] = self._evaluation_metadata(pool_evaluation)
        state.add_event(
            "policy_evaluated",
            message=f"Pool policy decision: {pool_evaluation.decision}",
            metadata=state.metadata["pool_policy"],
        )

        if pool_evaluation.decision == "block":
            state.status = "blocked"
            state.blocked_item_ids = list(pool_evaluation.metadata.get("blocked_item_ids") or [])
            pool.status = "blocked"
            pool.blocked_item_ids = self._dedupe([*pool.blocked_item_ids, *state.blocked_item_ids])
            state.add_event("pipeline_blocked", message="Pool policy blocked the pipeline.")
            self._finish_state(state)
            self.storage.save_pool(pool)
            return state

        if pool_evaluation.decision == "require_approval":
            state.status = "paused"
            approval_ids = list(pool_evaluation.metadata.get("approval_required_item_ids") or [])
            state.metadata["approval_required_item_ids"] = approval_ids
            state.warnings.append("pool_policy_requires_approval")
            pool.status = "paused"
            pool.updated_at = _utc_now_iso()
            state.add_event(
                "pipeline_paused",
                message="Pool policy requires approval before pipeline execution.",
                metadata={"approval_required_item_ids": approval_ids},
            )
            self._finish_state(state)
            self.storage.save_pool(pool)
            return state

        processed_count = 0
        item_limit = self._effective_item_limit(request)
        while self.select_next_ready_item(pool) is not None:
            if item_limit is not None and processed_count >= item_limit:
                state.status = "paused"
                state.warnings.append("max_items_reached")
                state.metadata["max_items_reached"] = True
                state.add_event("pipeline_paused", message="Pipeline paused after reaching max_items.")
                break

            before_count = len(state.item_results)
            self.run_next_item(state, pool)
            if len(state.item_results) > before_count:
                processed_count += 1

            if state.status in {"blocked", "paused"}:
                break
            if state.status == "failed" and request.stop_on_failure:
                break
            if request.pause_after_each_item and processed_count > 0:
                state.status = "paused"
                state.warnings.append("pause_after_each_item")
                pool.status = "paused"
                state.add_event("pipeline_paused", message="Pipeline paused after one item.")
                break

        if state.status == "running":
            state.status = "completed"
            pool.status = "completed"
            state.add_event("pipeline_completed", message="Pipeline dry-run completed.")
        elif state.status == "failed":
            pool.status = "failed"
            state.add_event("pipeline_failed", message="Pipeline dry-run failed.")
        elif state.status == "blocked":
            pool.status = "blocked"
            state.add_event("pipeline_blocked", message="Pipeline dry-run blocked.")
        elif state.status == "paused":
            pool.status = "paused"

        self._sync_state_lists_from_pool(state, pool)
        self._finish_state(state)
        pool.updated_at = _utc_now_iso()
        self.storage.save_pool(pool)
        return state

    def run_next_item(self, state: AtlasPipelineRunState, pool: AtlasPlanPool) -> AtlasPipelineRunState:
        item = self.select_next_ready_item(pool)
        if item is None:
            return state

        state.current_item_id = item.item_id
        pool.current_item_id = item.item_id
        result = AtlasPipelineItemResult(item_id=item.item_id, status="policy_checking", started_at=_utc_now_iso())
        state.add_event("item_started", item_id=item.item_id, message="Pipeline item started.")

        evaluation = self.policy_gate.evaluate_item(item, pool)
        result.policy_decision = evaluation.decision
        result.policy_reasons = list(evaluation.reasons)
        result.policy_categories = list(evaluation.categories)
        result.warnings.extend(evaluation.warnings)
        state.add_event(
            "policy_evaluated",
            item_id=item.item_id,
            message=f"Item policy decision: {evaluation.decision}",
            metadata=self._evaluation_metadata(evaluation),
        )

        if evaluation.decision == "block":
            reason = "; ".join(evaluation.reasons)
            updated_pool = self.storage.mark_item_blocked(pool.pool_id, item.item_id, reason=reason)
            self._copy_pool_state(pool, updated_pool)
            result.status = "blocked"
            result.finished_at = _utc_now_iso()
            state.blocked_item_ids = self._dedupe([*state.blocked_item_ids, item.item_id])
            state.status = "blocked"
            state.item_results.append(result)
            state.add_event("item_blocked", item_id=item.item_id, message=reason or "Item blocked by policy.")
            self._sync_state_lists_from_pool(state, pool)
            return state

        if evaluation.decision == "require_approval":
            item.status = "approval_required"
            updates: dict[str, Any] = {"status": "approval_required"}
            event_metadata: dict[str, Any] = {}
            if self.approval_gate is not None:
                approval_record = self.approval_gate.request_approval(
                    scope="item",
                    pool_id=pool.pool_id,
                    item_id=item.item_id,
                    policy_evaluation=evaluation,
                )
                updates["approval_id"] = approval_record.approval_id
                result.warnings.append(f"approval_id:{approval_record.approval_id}")
                event_metadata["approval_id"] = approval_record.approval_id
            updated_pool = self.storage.update_item(pool.pool_id, item.item_id, **updates)
            self._copy_pool_state(pool, updated_pool)
            result.status = "approval_required"
            result.finished_at = _utc_now_iso()
            state.status = "paused"
            state.item_results.append(result)
            state.add_event(
                "pipeline_paused",
                item_id=item.item_id,
                message="Item requires approval before dry-run execution.",
                metadata=event_metadata,
            )
            self._sync_state_lists_from_pool(state, pool)
            return state

        try:
            item.status = "executing"
            updated_pool = self.storage.update_item(pool.pool_id, item.item_id, status="executing")
            self._copy_pool_state(pool, updated_pool)
            state.add_event("item_dry_run_started", item_id=item.item_id, message="Implementation dry-run started.")
            result.status = "dry_running"
            dry_run_result = self.call_implementation_dry_run(item, pool)
            result.dry_run_result = dry_run_result
            result.implementation_run_id = str(dry_run_result.get("run_id") or dry_run_result.get("implementation_run_id") or "")
            updated_pool = self.storage.mark_item_completed(pool.pool_id, item.item_id)
            self._copy_pool_state(pool, updated_pool)
            result.status = "completed"
            result.finished_at = _utc_now_iso()
            state.completed_item_ids = self._dedupe([*state.completed_item_ids, item.item_id])
            state.item_results.append(result)
            state.add_event("item_dry_run_completed", item_id=item.item_id, message="Implementation dry-run completed.")
            state.add_event("item_completed", item_id=item.item_id, message="Pipeline item completed.")
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            updated_pool = self.storage.mark_item_failed(pool.pool_id, item.item_id, error=error)
            self._copy_pool_state(pool, updated_pool)
            result.status = "failed"
            result.errors.append(error)
            result.finished_at = _utc_now_iso()
            state.failed_item_ids = self._dedupe([*state.failed_item_ids, item.item_id])
            state.status = "failed"
            state.item_results.append(result)
            state.add_event("item_failed", item_id=item.item_id, message=error)

        self._sync_state_lists_from_pool(state, pool)
        return state


    def evaluate_safe_apply_for_item(
        self,
        item: AtlasPlanItem,
        pool: AtlasPlanPool,
        patch_metadata: dict | None = None,
    ) -> AtlasSafeApplyResult:
        adapter = self.safe_apply_adapter or AtlasSafeApplyAdapter(
            policy_gate=self.policy_gate,
            approval_gate=self.approval_gate,
            implementation_executor=self.implementation_executor,
        )
        evaluate_method = getattr(adapter, "evaluate_" + "safe_apply")
        return evaluate_method(item, pool, patch_metadata=patch_metadata)

    def safe_apply_item_once(
        self,
        item: AtlasPlanItem,
        pool: AtlasPlanPool,
        request: AtlasSafeApplyRequest | None = None,
        patch_metadata: dict | None = None,
    ) -> AtlasSafeApplyResult:
        adapter = self.safe_apply_adapter or AtlasSafeApplyAdapter(
            policy_gate=self.policy_gate,
            approval_gate=self.approval_gate,
            implementation_executor=self.implementation_executor,
        )
        return adapter.apply_low_risk_item(item, pool, request=request, patch_metadata=patch_metadata)

    def run_item_tests(
        self,
        item: AtlasPlanItem,
        cwd: str = "",
        stop_on_failure: bool = True,
    ) -> AtlasTestCommandBatchResult:
        runner = self.test_command_runner or TestCommandRunner()
        return runner.run_item_tests(item, cwd=cwd, stop_on_failure=stop_on_failure)

    def select_next_ready_item(self, pool: AtlasPlanPool) -> AtlasPlanItem | None:
        ready_items = pool.get_ready_items()
        if not ready_items:
            return None
        return ready_items[0]

    def call_implementation_dry_run(self, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
        executor = self.implementation_executor
        if executor is None:
            return {
                "dry_run": True,
                "skipped_executor": True,
                "message": "No implementation executor provided; dry-run simulation only.",
                "item_id": item.item_id,
                "target_files": list(item.target_files),
            }

        dry_run_method = getattr(executor, "execute_plan_item_dry_run", None)
        if callable(dry_run_method):
            return self._dict_result(dry_run_method(item=item, pool=pool))

        execute_method = getattr(executor, "execute", None)
        if callable(execute_method):
            return self._dict_result(
                execute_method(
                    item=item,
                    pool=pool,
                    dry_run=True,
                    execution_mode="dry_run",
                )
            )

        raise TypeError("implementation_executor must provide a dry-run execution method")

    def _effective_item_limit(self, request: AtlasPipelineRunRequest) -> int | None:
        policy_limit = self.policy_gate.policy.max_items_per_run
        limits = [value for value in (request.max_items, policy_limit) if value is not None]
        if not limits:
            return None
        return min(limits)

    def _finish_state(self, state: AtlasPipelineRunState) -> None:
        state.finished_at = _utc_now_iso()
        state.updated_at = state.finished_at

    def _sync_state_lists_from_pool(self, state: AtlasPipelineRunState, pool: AtlasPlanPool) -> None:
        state.completed_item_ids = list(pool.completed_item_ids)
        state.blocked_item_ids = list(pool.blocked_item_ids)
        state.failed_item_ids = list(pool.failed_item_ids)
        state.skipped_item_ids = list(pool.skipped_item_ids)
        state.current_item_id = pool.current_item_id
        state.updated_at = _utc_now_iso()

    def _copy_pool_state(self, target: AtlasPlanPool, source: AtlasPlanPool) -> None:
        for field_name in self._model_field_names(target):
            setattr(target, field_name, getattr(source, field_name))

    def _request_metadata(self, request: AtlasPipelineRunRequest) -> dict[str, Any]:
        return {
            "run_id": request.run_id,
            "pool_id": request.pool_id,
            "ca_data_root": request.ca_data_root,
            "execution_strategy": request.execution_strategy,
            "max_items": request.max_items,
            "dry_run": request.dry_run,
            "safe_apply": request.safe_apply,
            "stop_on_failure": request.stop_on_failure,
            "pause_after_each_item": request.pause_after_each_item,
            "metadata": dict(request.metadata),
        }

    def _evaluation_metadata(self, evaluation: AtlasPolicyEvaluation) -> dict[str, Any]:
        return {
            "evaluation_id": evaluation.evaluation_id,
            "scope": evaluation.scope,
            "decision": evaluation.decision,
            "item_id": evaluation.item_id,
            "pool_id": evaluation.pool_id,
            "risk_level": evaluation.risk_level,
            "reasons": list(evaluation.reasons),
            "categories": list(evaluation.categories),
            "warnings": list(evaluation.warnings),
            "metadata": dict(evaluation.metadata),
        }

    def _dict_result(self, value: Any) -> dict:
        if value is None:
            return {"dry_run": True, "result": None}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "dict"):
            return value.dict()
        return {"dry_run": True, "result": value}

    def _model_field_names(self, model: Any) -> list[str]:
        model_type = model.__class__
        if hasattr(model_type, "model_fields"):
            return list(model_type.model_fields)
        return list(model_type.__fields__)

    def _dedupe(self, values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            if value and value not in deduped:
                deduped.append(value)
        return deduped
