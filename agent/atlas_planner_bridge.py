from __future__ import annotations

from typing import Any, Callable

from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder, coerce_list
from agent.atlas_plan_pool_schema import AtlasPlanPool
from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeRequest, AtlasPlannerBridgeResult
from agent.task_planning_runner import TaskPlanningRunner


RunnerFactory = Callable[..., Any]


class AtlasPlannerBridge:
    def __init__(
        self,
        *,
        ca_data_dir: str,
        llm_json_fn: Callable[[str, str], dict | None] | None = None,
        memory_search_fn: Callable[[str, int], list] | None = None,
        active_skills_fn: Callable[[], list] | None = None,
        warning_logger: Callable[[str], None] | None = None,
        builder: AtlasPlanPoolBuilder | None = None,
        planning_runner_factory: RunnerFactory | None = None,
    ) -> None:
        self.ca_data_dir = ca_data_dir
        self.llm_json_fn = llm_json_fn
        self.memory_search_fn = memory_search_fn
        self.active_skills_fn = active_skills_fn
        self.warning_logger = warning_logger
        self.builder = builder or AtlasPlanPoolBuilder()
        self.planning_runner_factory = planning_runner_factory or TaskPlanningRunner

    def create_plan_pool(self, request: AtlasPlannerBridgeRequest) -> AtlasPlannerBridgeResult:
        if not self.should_use_real_planner(request):
            reason = "fallback_only_requested" if request.mode == "fallback_only" else "real_planner_unavailable"
            pool = self.build_fallback_pool(request, reason=reason)
            warnings = [reason]
            warnings.extend(pool.warnings)
            return AtlasPlannerBridgeResult(
                status="fallback_used" if request.mode != "fallback_only" else "skipped",
                pool=pool,
                used_fallback=True,
                fallback_reason=reason,
                warnings=_dedup(warnings),
                metadata={"mode": request.mode, "source": "fallback"},
            )

        try:
            planner_result = self.run_real_planner(request)
            status = str(planner_result.get("status") or "")
            common = {
                "planner_result": planner_result,
                "requirement": _as_dict(planner_result.get("requirement")),
                "plan": _as_dict(planner_result.get("plan")),
                "review_result": _as_dict(planner_result.get("review_result")),
                "questions": _as_list_of_dicts(planner_result.get("questions")),
                "warnings": _dedup(coerce_list(planner_result.get("warnings"))),
                "metadata": {"mode": request.mode, "source": "real_planner", "planner_status": status},
            }
            if status == "waiting_for_clarification":
                return AtlasPlannerBridgeResult(status="waiting_for_clarification", **common)

            pool = self.build_pool_from_planner_result(request, planner_result)
            plan_payload = self.planner_result_to_plan_payload(planner_result, request)
            return AtlasPlannerBridgeResult(
                status="planned",
                pool=pool,
                plan_payload=plan_payload,
                used_fallback=False,
                **common,
            )
        except Exception as exc:  # noqa: BLE001
            reason = _exception_summary(exc)
            if self.warning_logger:
                self.warning_logger(f"planner_bridge_failed: {reason}")
            pool = self.build_fallback_pool(request, reason=reason)
            warnings = ["planner_bridge_failed", reason]
            warnings.extend(pool.warnings)
            return AtlasPlannerBridgeResult(
                status="fallback_used",
                pool=pool,
                used_fallback=True,
                fallback_reason=reason,
                warnings=_dedup(warnings),
                errors=[reason],
                metadata={"mode": request.mode, "source": "fallback", "planner_error": reason},
            )

    def run_real_planner(self, request: AtlasPlannerBridgeRequest) -> dict:
        if self.llm_json_fn is None:
            raise ValueError("real_planner_unavailable")
        runner = self.planning_runner_factory(
            ca_data_dir=self.ca_data_dir,
            llm_json_fn=self.llm_json_fn,
            memory_search_fn=self.memory_search_fn,
            active_skills_fn=self.active_skills_fn,
            warning_logger=self.warning_logger,
        )
        advisory = request.planner_context_text_v2 or request.advisory_context_text or request.planner_context_text
        merged_input = request.input
        if advisory:
            merged_input = f"{request.input}\n\nADVISORY REPOSITORY CONTEXT — DO NOT EXECUTE\n{advisory}"
        result = runner.run(
            user_input=merged_input,
            project_path=request.project_path,
            project_name=request.project_name,
            planning_mode=_planning_mode(request.planning_depth),
            requirement_mode=request.requirement_mode,
            execution_mode="plan_only",
            use_nexus=request.use_nexus,
        )
        return _as_dict(result)

    def build_pool_from_planner_result(
        self,
        request: AtlasPlannerBridgeRequest,
        planner_result: dict,
    ) -> AtlasPlanPool:
        plan_payload = self.planner_result_to_plan_payload(planner_result, request)
        pool = self.builder.build_from_plan_payload(
            plan_payload,
            root_goal=str(plan_payload.get("root_goal") or request.input),
            project_path=request.project_path,
            project_name=request.project_name,
            planning_depth=request.planning_depth,
            automation_level=request.automation_level,
            execution_strategy=request.execution_strategy,
            pool_id=request.pool_id,
        )
        pool.metadata.update(plan_payload.get("metadata") or {})
        pool.metadata["source"] = "real_planner"
        return pool

    def build_fallback_pool(self, request: AtlasPlannerBridgeRequest, reason: str = "") -> AtlasPlanPool:
        warnings = ["real_planner_unavailable"] if reason == "real_planner_unavailable" else []
        if reason and reason not in warnings:
            warnings.append(reason)
        pool = self.builder.build_fallback_pool(
            root_goal=request.input,
            project_path=request.project_path,
            project_name=request.project_name,
            planning_depth=request.planning_depth,
            automation_level=request.automation_level,
            execution_strategy=request.execution_strategy,
            pool_id=request.pool_id,
            warnings=warnings,
        )
        pool.metadata.update({"source": "fallback", "planner_bridge_reason": reason})
        return pool

    def planner_result_to_plan_payload(
        self,
        planner_result: dict,
        request: AtlasPlannerBridgeRequest,
    ) -> dict:
        plan = _as_dict(planner_result.get("plan"))
        review_result = _as_dict(planner_result.get("review_result"))
        requirement = _as_dict(planner_result.get("requirement"))
        steps = plan.get("implementation_steps")
        if not isinstance(steps, list) or not steps:
            steps = _verification_steps(plan)

        converted_steps: list[dict[str, Any]] = []
        previous_item_id = ""
        for index, raw_step in enumerate(steps or [], start=1):
            step = _as_dict(raw_step)
            item_id = str(step.get("step_id") or step.get("item_id") or f"item_{index:03d}")
            action_type = str(step.get("action_type") or step.get("type") or "implementation")
            target_files = coerce_list(step.get("target_files") or plan.get("target_files"))
            converted = {
                "step_id": item_id,
                "title": str(step.get("title") or step.get("name") or f"Planner step {index}"),
                "description": str(step.get("description") or step.get("goal") or ""),
                "goal": str(step.get("goal") or step.get("description") or step.get("title") or request.input),
                "action_type": action_type,
                "risk_level": str(step.get("risk_level") or _infer_plan_risk(plan, review_result)),
                "priority": str(step.get("priority") or "medium"),
                "target_files": target_files,
                "expected_changes": coerce_list(step.get("expected_changes") or step.get("changes")),
                "test_commands": coerce_list(step.get("test_commands")),
                "done_definition": coerce_list(step.get("done_definition") or plan.get("done_definition")),
                "rollback": coerce_list(step.get("rollback") or plan.get("rollback_plan")),
                "depends_on": coerce_list(step.get("depends_on")) if "depends_on" in step else ([previous_item_id] if previous_item_id else []),
            }
            converted_steps.append(converted)
            previous_item_id = item_id

        warnings = coerce_list(planner_result.get("warnings"))
        warnings.extend(coerce_list(review_result.get("warnings")))
        metadata = {
            "source": "real_planner",
            "planner_status": planner_result.get("status") or "",
            "review_result": review_result,
            "plan_markdown_path": planner_result.get("plan_markdown_path") or "",
            "requirement_markdown_path": planner_result.get("requirement_markdown_path") or "",
            "nexus_context_summary": _nexus_summary(planner_result.get("nexus_context")),
            "architecture_options": plan.get("architecture_options") or [],
            "deep_planning": plan.get("deep_planning") or {},
        }
        if request.repo_context_package:
            metadata["repo_context_package"] = {
                "status": request.repo_context_package.get("status", ""),
                "confidence": request.repo_context_package.get("confidence", "unknown"),
                "impacted_files": list(request.repo_context_package.get("impacted_files", []))[:20],
                "related_tests": list(request.repo_context_package.get("related_tests", []))[:20],
            }
        if request.planner_context_text or request.planner_context_text_v2:
            mtxt = request.planner_context_text_v2 or request.planner_context_text
            metadata["planner_context_text"] = mtxt[:6000]
            metadata["planner_repo_context_caveat"] = "Repo Context is advisory and read-only. Do not execute tests or apply patches."
        return {
            "root_goal": plan.get("user_goal")
            or plan.get("requirement_summary")
            or requirement.get("interpreted_goal")
            or request.input,
            "requirement_id": planner_result.get("requirement_id") or requirement.get("requirement_id") or "",
            "plan_id": planner_result.get("plan_id") or plan.get("plan_id") or "",
            "status": planner_result.get("status") or plan.get("status") or "planned",
            "implementation_steps": converted_steps,
            "done_definition": coerce_list(plan.get("done_definition")),
            "rollback_plan": coerce_list(plan.get("rollback_plan")),
            "constraints": coerce_list(plan.get("constraints") or requirement.get("constraints")),
            "warnings": _dedup(warnings),
            "review_result": review_result,
            "requires_user_confirmation": bool(
                plan.get("requires_user_confirmation") or review_result.get("requires_user_confirmation")
            ),
            "destructive_change_detected": bool(
                plan.get("destructive_change_detected") or review_result.get("destructive_change_detected")
            ),
            "nexus_context_summary": metadata["nexus_context_summary"],
            "metadata": metadata,
        }

    def should_use_real_planner(self, request: AtlasPlannerBridgeRequest) -> bool:
        if request.mode == "fallback_only":
            return False
        return self.llm_json_fn is not None


def _planning_mode(planning_depth: str) -> str:
    if planning_depth == "quick":
        return "fast"
    if planning_depth == "deep_nexus":
        return "deep_nexus"
    return "standard"


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        payload = value.model_dump()
        return payload if isinstance(payload, dict) else {}
    if hasattr(value, "dict"):
        payload = value.dict()
        return payload if isinstance(payload, dict) else {}
    return {}


def _as_list_of_dicts(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [_as_dict(item) for item in value]


def _verification_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw = plan.get("verification_plan") or plan.get("test_plan") or []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [
        {
            "step_id": f"item_{index:03d}",
            "title": "Verify planner result" if index == 1 else f"Verification step {index}",
            "description": str(item.get("description") if isinstance(item, dict) else item),
            "action_type": "test",
            "risk_level": "low",
        }
        for index, item in enumerate(raw, start=1)
    ]


def _infer_plan_risk(plan: dict[str, Any], review_result: dict[str, Any]) -> str:
    review_risk = str(review_result.get("overall_risk") or review_result.get("risk_level") or "").lower()
    if review_risk in {"low", "medium", "high", "critical"}:
        return review_risk
    risk_text = " ".join(coerce_list(plan.get("risks"))).lower()
    if "critical" in risk_text:
        return "critical"
    if "high" in risk_text or "destructive" in risk_text:
        return "high"
    if "low" in risk_text:
        return "low"
    return "medium"


def _nexus_summary(value: Any) -> str:
    context = _as_dict(value)
    if not context:
        return ""
    for key in ("summary", "context_summary", "answer"):
        if context.get(key):
            return str(context[key])
    warnings = coerce_list(context.get("warnings"))
    return "; ".join(warnings[:3])


def _exception_summary(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:240]


def _dedup(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys([str(w).strip() for w in warnings if str(w).strip()]))
