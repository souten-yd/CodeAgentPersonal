from __future__ import annotations

import re
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
        progress_cb: Callable[..., None] | None = None,
    ) -> None:
        self.ca_data_dir = ca_data_dir
        self.llm_json_fn = llm_json_fn
        self.memory_search_fn = memory_search_fn
        self.active_skills_fn = active_skills_fn
        self.warning_logger = warning_logger
        self.builder = builder or AtlasPlanPoolBuilder()
        self.planning_runner_factory = planning_runner_factory or TaskPlanningRunner
        self.progress_cb = progress_cb

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
            # Fold research_findings / adversarial_critique into the plan dict so downstream consumers
            # (e.g. the strategic-plan summary) can surface them without a wider schema change.
            _plan_dict = _as_dict(planner_result.get("plan"))
            if isinstance(planner_result.get("research_findings"), dict):
                _plan_dict.setdefault("research_findings", planner_result.get("research_findings"))
            if isinstance(planner_result.get("adversarial_critique"), dict):
                _plan_dict.setdefault("adversarial_critique", planner_result.get("adversarial_critique"))
            common = {
                "planner_result": planner_result,
                "requirement": _as_dict(planner_result.get("requirement")),
                "plan": _plan_dict,
                "review_result": _as_dict(planner_result.get("review_result")),
                "questions": _as_list_of_dicts(planner_result.get("questions")),
                "warnings": _dedup(coerce_list(planner_result.get("warnings"))),
                "metadata": {"mode": request.mode, "source": "real_planner", "planner_status": status},
            }
            if status == "waiting_for_clarification":
                return AtlasPlannerBridgeResult(status="waiting_for_clarification", **common)

            pool = self.build_pool_from_planner_result(request, planner_result)
            self._prime_project_twin(request, pool)
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
            progress_cb=self.progress_cb,
        )
        advisory = request.planner_context_text_v2 or request.advisory_context_text or request.planner_context_text
        # Model-capability-driven file decomposition: a weak model gets a smaller per-file budget and
        # is told to split more; a frontier model is allowed large / single-file deliverables. Advisory
        # only, best-effort, disabled-safe (no-op when no profile and an unknown model).
        decomposition = self._decomposition_directive(request)
        if decomposition:
            advisory = f"{advisory}\n\n{decomposition}" if advisory else decomposition
        result = runner.run(
            user_input=request.input,
            project_path=request.project_path,
            project_name=request.project_name,
            planning_mode=_planning_mode(request.planning_depth),
            requirement_mode=request.requirement_mode,
            execution_mode="plan_only",
            use_nexus=request.use_nexus,
            advisory_context=advisory,
            progress_cb=self.progress_cb,
        )
        return _as_dict(result)

    def _prime_project_twin(self, request: AtlasPlannerBridgeRequest, pool: AtlasPlanPool) -> None:
        """Plan-time Project Twin priming: build/refresh the persistent dependency graph as soon as
        the plan exists, keyed by the pool_id the codegen run will use, so impact / Safe-Edit
        Briefing evidence is ready BEFORE generation — the run then reuses it via load-first instead
        of building mid-run. This is what makes the Twin effectively "always on from plan time" on a
        large existing codebase. Always-on for an existing project under the same active-mode +
        autobuild defaults the orchestrator uses; a greenfield/empty path is a no-op. Best-effort and
        disabled-safe: it never raises and never blocks planning."""
        try:
            from agent.twin_control_plane.pipeline_integration import (
                PipelineMode, ensure_project_twin, resolve_build_project_twin,
                resolve_pipeline_mode, resolve_twin_autobuild,
            )

            project_path = str(getattr(request, "project_path", "") or "")
            project_id = str(getattr(pool, "pool_id", "") or "")
            if not (project_path and project_id):
                return  # greenfield / no concrete pool: nothing to map yet.
            mode = resolve_pipeline_mode()
            if not (resolve_build_project_twin() or (mode == PipelineMode.ACTIVE and resolve_twin_autobuild())):
                return  # Twin autobuild disabled: stay on the legacy load-only path.
            ensure_project_twin(
                data_root=str(self.ca_data_dir), project_id=project_id, project_path=project_path)
        except Exception:  # noqa: BLE001 - priming is advisory; never block planning.
            return

    def _decomposition_directive(self, request: AtlasPlannerBridgeRequest) -> str:
        """Model-specific file-decomposition budget for the planner advisory. Best-effort: resolves the
        active model + its Forge capability profile and renders a sizing directive. Returns "" on any
        problem so planning is never blocked. With no profile and an unknown model this yields the
        balanced ``standard`` tier (the same defaults the static prompt already used)."""
        try:
            import os
            from pathlib import Path
            from agent.model_forge.decomposition_policy import (
                derive_decomposition_policy, render_decomposition_directive,
            )

            md = request.metadata if isinstance(request.metadata, dict) else {}
            model_id = str(
                md.get("model_id")
                or getattr(self.llm_json_fn, "model", "")
                or os.environ.get("CODEAGENT_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or os.environ.get("FORGE_LOCAL_MODEL")
                or ""
            ).strip()
            provider_id = str(md.get("provider_id") or "local").strip() or "local"
            # When the request/env did not pin a model, resolve the Forge-evaluated identity (the same
            # seam the orchestrator uses) so the planner sizes for the model that will actually run —
            # including a live :8080 probe when opted in. Identity only; best-effort.
            if not model_id:
                try:
                    from agent.model_forge.forge_service import ForgeService

                    probe_live = os.environ.get("ATLAS_FORGE_PROBE_LOCAL", "").strip().lower() in {"1", "on", "true", "yes"}
                    resolved = ForgeService(self.ca_data_dir, env=os.environ).resolve_active_codegen_model(probe_live=probe_live)
                    model_id = str(resolved.get("model_id") or "").strip()
                    if model_id:
                        provider_id = str(resolved.get("provider_id") or provider_id).strip() or provider_id
                except Exception:  # noqa: BLE001 - resolution is advisory; keep the name heuristic.
                    pass
            capability_scores: dict = {}
            known_weaknesses: tuple = ()
            if model_id:
                try:
                    from agent.model_forge.capability_scoring import load_capability_profile
                    from agent.model_forge.profile_store import ProfileStore

                    store = ProfileStore(Path(self.ca_data_dir) / "model_forge" / "profiles")
                    cap = load_capability_profile(store, provider_id, model_id)
                    capability_scores = dict(getattr(cap, "capability_scores", {}) or {})
                    known_weaknesses = tuple(getattr(cap, "known_weaknesses", ()) or ())
                except Exception:  # noqa: BLE001 - profile is advisory; fall back to the name heuristic.
                    pass
            policy = derive_decomposition_policy(
                capability_scores=capability_scores,
                known_weaknesses=known_weaknesses,
                model_id=model_id,
            )
            return render_decomposition_directive(policy)
        except Exception:  # noqa: BLE001 - never block planning on the advisory directive.
            return ""

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
        requirement_trace = _requirements_from_planner_result(planner_result, requirement)
        steps = plan.get("implementation_steps")
        if not isinstance(steps, list) or not steps:
            steps = _verification_steps(plan)

        converted_steps: list[dict[str, Any]] = []
        previous_item_id = ""
        for index, raw_step in enumerate(steps or [], start=1):
            step = _as_dict(raw_step)
            item_id = str(step.get("step_id") or step.get("item_id") or f"item_{index:03d}")
            action_type = str(step.get("action_type") or step.get("type") or "implementation")
            target_files = coerce_list(step.get("target_files"))
            target_directories = coerce_list(step.get("target_directories"))
            if not target_files and not target_directories:
                target_files = coerce_list(plan.get("target_files"))
                target_directories = coerce_list(plan.get("target_directories"))
            acceptance_criteria = coerce_list(step.get("acceptance_criteria") or step.get("done_definition"))
            requirement_ids = coerce_list(step.get("requirement_ids") or step.get("linked_requirement_ids") or step.get("requirement_id") or step.get("linked_requirement_id"))
            if not requirement_ids and str(request.automation_level or "").lower() == "full_autopilot":
                requirement_ids = _infer_step_requirement_ids(step, requirement_trace)
            verification_contract = _verification_contract(step)
            if not verification_contract and str(request.automation_level or "").lower() == "full_autopilot":
                verification_contract = _default_verification_contract(step, plan)
            converted = {
                "schema_version": str(step.get("schema_version") or plan.get("schema_version") or ""),
                "step_id": item_id,
                "title": str(step.get("title") or step.get("name") or f"Planner step {index}"),
                "description": str(step.get("description") or step.get("goal") or ""),
                "goal": str(step.get("goal") or step.get("description") or step.get("title") or request.input),
                "patch_task_kind": str(step.get("patch_task_kind") or plan.get("patch_task_kind") or ""),
                "action_type": action_type,
                "risk_level": str(step.get("risk_level") or _infer_plan_risk(plan, review_result)),
                "priority": str(step.get("priority") or "medium"),
                "target_files": target_files,
                "target_directories": target_directories,
                "operations": list(step.get("operations") or []),
                "assumptions": coerce_list(step.get("assumptions") or plan.get("assumptions")),
                "normalization_diagnostics": list(step.get("normalization_diagnostics") or []),
                "requirement_ids": requirement_ids,
                "acceptance_criteria": acceptance_criteria,
                "expected_changes": coerce_list(step.get("expected_changes") or step.get("changes")),
                "test_commands": coerce_list(step.get("test_commands")),
                "done_definition": coerce_list(step.get("done_definition") or acceptance_criteria or plan.get("done_definition")),
                "verification": step.get("verification") or "",
                "verification_contract": verification_contract,
                "rollback": coerce_list(step.get("rollback") or plan.get("rollback_plan")),
                "preserve_behaviors": coerce_list(step.get("preserve_behaviors") or plan.get("preserve_behaviors") or requirement.get("preserve_behaviors")),
                "depends_on": coerce_list(step.get("depends_on")) if "depends_on" in step else ([previous_item_id] if previous_item_id else []),
            }
            if isinstance(step.get("file_changes"), list):
                converted["file_changes"] = step.get("file_changes")
            if isinstance(step.get("change_set"), dict):
                converted["change_set"] = step.get("change_set")
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
            "selected_architecture": plan.get("selected_architecture") or requirement.get("selected_architecture") or "",
            "deep_planning": plan.get("deep_planning") or {},
            "global_constraints": coerce_list(plan.get("constraints") or requirement.get("constraints")),
            "preserve_behaviors": coerce_list(plan.get("preserve_behaviors") or requirement.get("preserve_behaviors")),
            "requirement_trace": requirement_trace,
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
            "original_user_request": requirement.get("user_input") or request.input,
            "root_goal": plan.get("user_goal")
            or plan.get("requirement_summary")
            or requirement.get("interpreted_goal")
            or request.input,
            "selected_architecture": metadata["selected_architecture"],
            "requirements": requirement_trace,
            "preserve_behaviors": metadata["preserve_behaviors"],
            "requirement_id": planner_result.get("requirement_id") or requirement.get("requirement_id") or "",
            "plan_id": planner_result.get("plan_id") or plan.get("plan_id") or "",
            "status": planner_result.get("status") or plan.get("status") or "planned",
            "implementation_steps": converted_steps,
            "schema_version": str(plan.get("schema_version") or ""),
            "patch_task_kind": str(plan.get("patch_task_kind") or ""),
            "target_files": coerce_list(plan.get("target_files")),
            "target_directories": coerce_list(plan.get("target_directories")),
            "operations": list(plan.get("operations") or []),
            "normalization_diagnostics": list(plan.get("normalization_diagnostics") or []),
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


def _verification_contract(step: dict[str, Any]) -> dict[str, Any]:
    raw = step.get("verification_contract")
    if isinstance(raw, dict):
        return dict(raw)
    verification = step.get("verification")
    if isinstance(verification, dict):
        return dict(verification)
    if str(verification or "").strip():
        return {"description": str(verification).strip()}
    return {}


def _default_verification_contract(step: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        *coerce_list(step.get("test_commands")),
        *coerce_list(step.get("verification")),
        *coerce_list(plan.get("test_plan")),
        *coerce_list(plan.get("verification_plan")),
        *coerce_list(step.get("acceptance_criteria") or step.get("done_definition")),
        *coerce_list(plan.get("done_definition")),
    ]
    text = "; ".join(str(value).strip() for value in candidates if str(value).strip())
    if not text:
        return {}
    return {
        "contract_id": "planner_derived_verification",
        "description": text[:1000],
        "source": "planner_bridge_full_autopilot_repair",
    }


def _infer_step_requirement_ids(step: dict[str, Any], requirements: list[dict[str, Any]]) -> list[str]:
    required = [
        req for req in requirements
        if isinstance(req, dict)
        and str(req.get("requirement_id") or "").strip()
        and req.get("required", True) is not False
    ]
    if not required:
        return []
    step_text = " ".join(
        [
            str(step.get("title") or ""),
            str(step.get("description") or ""),
            str(step.get("goal") or ""),
            " ".join(coerce_list(step.get("acceptance_criteria") or step.get("done_definition"))),
            " ".join(coerce_list(step.get("target_files"))),
        ]
    ).lower()
    matched: list[str] = []
    for req in required:
        req_id = str(req.get("requirement_id") or "").strip()
        req_text = " ".join(
            [
                str(req.get("description") or ""),
                str(req.get("title") or ""),
                str(req.get("goal") or ""),
            ]
        ).lower()
        tokens = {token for token in re.findall(r"[a-z0-9_]{4,}", req_text) if token not in {"must", "with", "that", "this"}}
        if tokens and any(token in step_text for token in tokens):
            matched.append(req_id)
    if matched:
        return list(dict.fromkeys(matched))
    return [str(req.get("requirement_id") or "").strip() for req in required]


def _requirements_from_planner_result(planner_result: dict, requirement: dict) -> list[dict[str, Any]]:
    candidates = (
        planner_result.get("requirements")
        or planner_result.get("requirement_trace")
        or requirement.get("requirements")
        or requirement.get("requirement_items")
    )
    if isinstance(candidates, list) and candidates:
        out: list[dict[str, Any]] = []
        for index, raw in enumerate(candidates, start=1):
            if isinstance(raw, dict):
                req = dict(raw)
                description = str(req.get("description") or req.get("title") or req.get("goal") or "").strip()
                if not description:
                    continue
                req.setdefault("requirement_id", str(req.get("id") or f"req_{index:03d}"))
                req["description"] = description
                req.setdefault("required", True)
                out.append(req)
            elif str(raw).strip():
                out.append({"requirement_id": f"req_{index:03d}", "description": str(raw).strip(), "required": True})
        if out:
            return out
    out = []
    for index, text in enumerate(coerce_list(requirement.get("functional_requirements")), start=1):
        out.append({"requirement_id": f"req_{index:03d}", "description": text, "required": True, "source": "functional_requirements"})
    return out


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
