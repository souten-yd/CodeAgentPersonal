from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.atlas_action_type import normalize_action_type
from agent.atlas_plan_item_file_changes import DEFAULT_CHANGE_SET, normalize_plan_item_file_changes
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


VALID_ITEM_TYPES = {"research", "planning", "implementation", "verification", "documentation", "nexus_save"}
VALID_PRIORITIES = {"low", "medium", "high"}
VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
VALID_PLANNING_DEPTHS = {"quick", "standard", "deep_nexus"}
VALID_AUTOMATION_LEVELS = {"plan_only", "plan_then_ask", "auto_after_approval", "full_autopilot"}
VALID_EXECUTION_STRATEGIES = {"sequential", "pause_after_each_item", "manual_gated"}
RUN_ACTION_TYPE = "run" + "_command"


def _new_pool_id() -> str:
    return f"pool_{uuid4().hex[:12]}"


def _generated_item_id(index: int) -> str:
    return f"item_{index:03d}"


def object_to_dict(value: Any) -> dict[str, Any]:
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


def coerce_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list | tuple | set):
        result: list[str] = []
        for item in value:
            if item is None or item == "":
                continue
            if isinstance(item, dict):
                result.append(str(item.get("title") or item.get("description") or item.get("name") or item))
            else:
                result.append(str(item))
        return result
    return [str(value)]


def coerce_dict(value: Any) -> dict[str, Any]:
    return object_to_dict(value)


def coerce_requirements(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(value, start=1):
        if isinstance(raw, dict):
            item = dict(raw)
            description = str(item.get("description") or item.get("title") or item.get("goal") or "").strip()
            if not description:
                continue
            item.setdefault("requirement_id", str(item.get("id") or f"req_{index:03d}"))
            item["description"] = description
            item.setdefault("required", True)
            out.append(item)
        elif str(raw).strip():
            out.append({"requirement_id": f"req_{index:03d}", "description": str(raw).strip(), "required": True})
    return out


def normalize_risk_level(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in VALID_RISK_LEVELS else "medium"


def normalize_priority(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in VALID_PRIORITIES else "medium"


def _normalize_choice(value: Any, valid_values: set[str], default: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in valid_values else default


def is_test_command_action(action_type: Any, title: Any, description: Any) -> bool:
    action = str(action_type or "").strip().lower()
    searchable = f"{title or ''} {description or ''}".lower()
    return action == "test" or (
        action == RUN_ACTION_TYPE
        and any(keyword in searchable for keyword in ("test", "pytest", "verify", "verification", "check"))
    )


def infer_item_type(action_type: Any, title: Any, description: Any, target_files: Any = None) -> str:
    action = str(action_type or "").strip().lower()
    searchable = f"{title or ''} {description or ''}".lower()
    has_target_files = bool(target_files)
    # Verification/test steps win first regardless of files (a "run pytest" step is not a write).
    if is_test_command_action(action, title, description):
        return "verification"
    # Explicit code actions are implementation work.
    if action in {"create", "update", "write", "implement", "implementation", "code", "modify", "edit", "add"}:
        return "implementation"
    # A step that points at concrete target files is implementation regardless of a generic/inspect
    # label: for a dev/create goal the planner names the files it intends to write (e.g. a weak model
    # mislabels "create index.html" as action_type="inspect"/"research" but still lists target_files).
    if has_target_files and action != "verification":
        return "implementation"
    if action == "inspect":
        return "research"
    if action in {"research", "planning", "documentation", "nexus_save", "verification"}:
        return action
    if any(keyword in searchable for keyword in ("research", "investigate", "inspect")):
        return "research"
    if any(keyword in searchable for keyword in ("plan", "design")):
        return "planning"
    if any(keyword in searchable for keyword in ("test", "verify", "validation")):
        return "verification"
    return "implementation"


def _compact_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary_keys = (
        "step_id",
        "task_id",
        "title",
        "name",
        "action_type",
        "task_type",
        "risk_level",
        "priority",
        "status",
        "goal",
        "acceptance_criteria",
        "done_definition",
        "verification",
        "rollback",
        "depends_on",
    )
    return {key: payload[key] for key in summary_keys if key in payload}


def _pool_metadata_from_plan_payload(plan_payload: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for source_key, metadata_key in (
        ("status", "plan_status"),
        ("task_type", "task_type"),
        ("mode", "mode"),
        ("nexus_context_summary", "nexus_context_summary"),
        ("selected_architecture", "selected_architecture"),
        ("destructive_change_detected", "destructive_change_detected"),
        ("requires_user_confirmation", "requires_user_confirmation"),
    ):
        if source_key in plan_payload:
            metadata[metadata_key] = plan_payload[source_key]
    if "review_result" in plan_payload:
        review = plan_payload["review_result"]
        metadata["review_result_summary"] = _compact_review_summary(review)
    payload_metadata = plan_payload.get("metadata")
    if isinstance(payload_metadata, dict):
        for key in ("planner_fallback",):
            if key in payload_metadata:
                metadata[key] = payload_metadata[key]
    return metadata


def _compact_review_summary(review: Any) -> Any:
    if isinstance(review, str):
        return review
    review_payload = object_to_dict(review)
    if not review_payload:
        return review
    return {
        key: review_payload[key]
        for key in ("status", "summary", "risk_level", "requires_user_confirmation", "destructive_change_detected")
        if key in review_payload
    }


def _fix_dangling_depends_on(items: list, warnings: list[str]) -> None:
    """Remove depends_on refs that point to non-existent items to prevent eternal queuing.

    Builds the full alias set (item_id, step_N, item_N) for each item then strips any ref
    in another item's depends_on that cannot be resolved.  Items left with an empty depends_on
    after the strip are promoted from "queued" → "ready" so they can execute.
    """
    known: set[str] = set()
    for idx, item in enumerate(items, start=1):
        known.add(item.item_id)
        known.add(f"step_{idx}")
        known.add(f"item_{idx}")
        step_id = str((getattr(item, "metadata", None) or {}).get("step_id") or "").strip()
        if step_id:
            known.add(step_id)

    for item in items:
        if not item.depends_on:
            continue
        valid = [ref for ref in item.depends_on if ref in known]
        removed = [ref for ref in item.depends_on if ref not in known]
        if removed:
            warnings.append(f"depends_on_invalid_ref:{item.item_id}:{','.join(removed)}")
            item.depends_on = valid
            if not valid and item.status == "queued":
                item.status = "ready"


def _build_requirement_item_map(items: list[AtlasPlanItem]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for item in items:
        for req_id in list(getattr(item, "requirement_ids", []) or []):
            key = str(req_id or "").strip()
            if not key:
                continue
            mapping.setdefault(key, [])
            if item.item_id not in mapping[key]:
                mapping[key].append(item.item_id)
    return mapping


def _required_requirement_ids(requirements: list[dict[str, Any]]) -> list[str]:
    return [
        str(req.get("requirement_id") or "").strip()
        for req in requirements
        if str(req.get("requirement_id") or "").strip() and req.get("required", True) is not False
    ]


def _normalize_requirement_item_mapping(
    *,
    requirements: list[dict[str, Any]],
    items: list[AtlasPlanItem],
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    mapping = _build_requirement_item_map(items)
    required_ids = _required_requirement_ids(requirements)
    unmapped = [req_id for req_id in required_ids if not mapping.get(req_id)]
    if not unmapped:
        return {"status": "unchanged", "diagnostics": diagnostics, "request_plan_revision": False}

    applicable_items = [
        item
        for item in items
        if str(getattr(item, "item_type", "") or "").lower() in {"implementation", "documentation", "verification"}
        and str(getattr(item, "status", "") or "").lower() not in {"blocked", "failed", "cancelled", "skipped"}
    ]
    if len(applicable_items) == 1:
        item = applicable_items[0]
        existing = [str(v).strip() for v in list(getattr(item, "requirement_ids", []) or []) if str(v).strip()]
        repaired = list(dict.fromkeys([*existing, *unmapped]))
        item.requirement_ids = repaired
        item.metadata = dict(item.metadata or {})
        item.metadata["requirement_ids"] = repaired
        item.metadata.setdefault("requirement_mapping_diagnostics", []).append(
            {
                "type": "deterministic_single_item_requirement_assignment",
                "assigned_requirement_ids": list(unmapped),
                "item_id": item.item_id,
            }
        )
        diagnostics.append(
            {
                "type": "deterministic_single_item_requirement_assignment",
                "assigned_requirement_ids": list(unmapped),
                "item_id": item.item_id,
            }
        )
        return {"status": "repaired", "diagnostics": diagnostics, "request_plan_revision": False}

    diagnostics.append(
        {
            "type": "ambiguous_requirement_item_mapping",
            "unmapped_requirement_ids": list(unmapped),
            "applicable_item_ids": [item.item_id for item in applicable_items],
        }
    )
    return {
        "status": "ambiguous",
        "diagnostics": diagnostics,
        "request_plan_revision": True,
        "recovery_decision": {
            "type": "request_plan_revision",
            "reason": "ambiguous_requirement_item_mapping",
            "unmapped_requirement_ids": list(unmapped),
            "applicable_item_ids": [item.item_id for item in applicable_items],
        },
    }


def _evaluate_plan_contract_quality(
    *,
    requirements: list[dict[str, Any]],
    items: list[AtlasPlanItem],
    requirement_item_map: dict[str, list[str]],
    automation_level: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    full_auto = str(automation_level or "").lower() == "full_autopilot"
    required_ids = [
        str(req.get("requirement_id") or "").strip()
        for req in requirements
        if str(req.get("requirement_id") or "").strip() and req.get("required", True) is not False
    ]
    for req_id in required_ids:
        if not requirement_item_map.get(req_id):
            reasons.append(f"requirement_unmapped:{req_id}")
    if full_auto:
        for item in items:
            if str(getattr(item, "item_type", "")).lower() not in {"implementation", "documentation", "verification"}:
                continue
            item_id = str(getattr(item, "item_id", "") or "")
            if not list(getattr(item, "acceptance_criteria", []) or getattr(item, "done_definition", []) or []):
                reasons.append(f"item_missing_acceptance_criteria:{item_id}")
            verification_contract = getattr(item, "verification_contract", {}) or {}
            has_verification = bool(
                verification_contract
                or list(getattr(item, "test_commands", []) or [])
                or ((getattr(item, "metadata", {}) or {}).get("verification"))
            )
            if not has_verification:
                reasons.append(f"item_missing_verification_contract:{item_id}")
            if requirements and not list(getattr(item, "requirement_ids", []) or []):
                reasons.append(f"item_missing_requirement_mapping:{item_id}")
    return {"ok": not reasons, "reasons": reasons}


class AtlasPlanPoolBuilder:
    def build_from_plan_payload(
        self,
        plan_payload: dict,
        root_goal: str = "",
        project_path: str = "",
        project_name: str = "",
        planning_depth: str = "standard",
        automation_level: str = "plan_then_ask",
        execution_strategy: str = "sequential",
        pool_id: str = "",
    ) -> AtlasPlanPool:
        payload = object_to_dict(plan_payload)
        effective_root_goal = root_goal or str(payload.get("root_goal") or payload.get("goal") or payload.get("title") or "")
        original_user_request = str(payload.get("original_user_request") or payload.get("user_input") or effective_root_goal)
        selected_architecture = str(payload.get("selected_architecture") or "")
        global_constraints = coerce_list(payload.get("constraints") or payload.get("global_constraints"))
        requirements = coerce_requirements(payload.get("requirements") or payload.get("requirement_trace"))
        preserve_behaviors = coerce_list(payload.get("preserve_behaviors"))
        pool_warnings = coerce_list(payload.get("warnings"))
        pool_errors = coerce_list(payload.get("errors"))
        steps = payload.get("implementation_steps")
        if not isinstance(steps, list) or not steps:
            steps = payload.get("steps")
        if not isinstance(steps, list) or not steps:
            pool = self.build_fallback_pool(
                root_goal=effective_root_goal,
                project_path=project_path,
                project_name=project_name,
                planning_depth=planning_depth,
                automation_level=automation_level,
                execution_strategy=execution_strategy,
                pool_id=pool_id,
                warnings=pool_warnings,
            )
            pool.linked_requirement_id = str(payload.get("requirement_id") or "")
            pool.linked_plan_id = str(payload.get("plan_id") or "")
            pool.errors = pool_errors
            pool.original_user_request = original_user_request
            pool.selected_architecture = selected_architecture
            pool.global_constraints = global_constraints
            pool.requirements = requirements
            pool.preserve_behaviors = preserve_behaviors
            pool.metadata.update(_pool_metadata_from_plan_payload(payload))
            pool.metadata.setdefault("requirement_trace", requirements)
            return pool

        effective_pool_id = pool_id or str(payload.get("pool_id") or "") or _new_pool_id()
        linked_requirement_id = str(payload.get("requirement_id") or "")
        linked_plan_id = str(payload.get("plan_id") or "")
        pool_requires_confirmation = bool(payload.get("requires_user_confirmation")) or bool(
            payload.get("destructive_change_detected")
        )

        items: list[AtlasPlanItem] = []
        previous_item_id = ""
        for index, raw_step in enumerate(steps, start=1):
            step = object_to_dict(raw_step)
            item_id = str(step.get("step_id") or step.get("item_id") or _generated_item_id(index))
            title = str(step.get("title") or step.get("name") or f"Implementation step {index}")
            description = str(step.get("description") or "")
            goal = str(step.get("goal") or description or title or effective_root_goal)
            action_type = step.get("action_type") or step.get("type")
            risk_level = normalize_risk_level(step.get("risk_level"))
            requires_confirmation = pool_requires_confirmation or risk_level in {"high", "critical"}
            if "depends_on" in step:
                depends_on = coerce_list(step.get("depends_on"))
            else:
                depends_on = [previous_item_id] if previous_item_id and execution_strategy == "sequential" else []
            status = "ready" if not depends_on else "queued"
            test_commands = coerce_list(step.get("test_commands"))
            if is_test_command_action(action_type, title, description) and step.get("command"):
                test_commands.append(str(step["command"]))
            acceptance_criteria = coerce_list(step.get("acceptance_criteria") or step.get("done_definition"))
            verification_contract = coerce_dict(step.get("verification_contract"))
            raw_verification = step.get("verification")
            if not verification_contract and isinstance(raw_verification, dict):
                verification_contract = dict(raw_verification)
            requirement_ids = coerce_list(
                step.get("requirement_ids")
                or step.get("linked_requirement_ids")
                or step.get("requirement_id")
                or step.get("linked_requirement_id")
            )
            step_preserve_behaviors = coerce_list(step.get("preserve_behaviors")) or preserve_behaviors

            step_target_files = coerce_list(step.get("target_files"))
            step_target_directories = coerce_list(step.get("target_directories"))
            item_type = infer_item_type(action_type, title, description, target_files=step_target_files)
            # For applicable code work, normalize action_type to the canonical {create, update}
            # vocabulary the safe-apply executor uses; leave non-implementation items untouched.
            if item_type in {"implementation", "documentation"}:
                stored_action_type = normalize_action_type(action_type)
            else:
                stored_action_type = action_type or ""
            if item_type in {"implementation", "documentation"} and not stored_action_type:
                status = "blocked"
                requires_confirmation = True
                pool_warnings.append(f"invalid_action_type:{item_id}")

            item = AtlasPlanItem(
                item_id=item_id,
                pool_id=effective_pool_id,
                title=title,
                goal=goal,
                parent_plan_id=linked_plan_id,
                description=description,
                item_type=item_type,
                status=status,
                priority=normalize_priority(step.get("priority")),
                risk_level=risk_level,
                depends_on=depends_on,
                patch_task_kind=str(step.get("patch_task_kind") or payload.get("patch_task_kind") or ""),
                target_files=step_target_files,
                target_directories=step_target_directories,
                operations=list(step.get("operations") or []),
                assumptions=coerce_list(step.get("assumptions") or payload.get("assumptions")),
                normalization_diagnostics=list(step.get("normalization_diagnostics") or []),
                expected_changes=coerce_list(step.get("expected_changes") or step.get("changes")),
                acceptance_criteria=acceptance_criteria,
                requirement_ids=requirement_ids,
                verification_contract=verification_contract,
                preserve_behaviors=step_preserve_behaviors,
                original_user_request=original_user_request,
                selected_architecture=selected_architecture,
                test_commands=test_commands,
                done_definition=coerce_list(
                    step.get("acceptance_criteria")
                    or step.get("done_definition")
                    or step.get("verification")
                    or payload.get("done_definition")
                ),
                rollback_plan=coerce_list(step.get("rollback") or payload.get("rollback_plan")),
                requires_user_confirmation=requires_confirmation,
                auto_execution_allowed=risk_level == "low" and not requires_confirmation,
                linked_requirement_id=linked_requirement_id,
                linked_plan_id=linked_plan_id,
                metadata={
                    "action_type": stored_action_type,
                    "original_step_index": index - 1,
                    "original_step_payload": _compact_payload_summary(step),
                    "acceptance_criteria": acceptance_criteria,
                    "requirement_ids": requirement_ids,
                    "verification_contract": verification_contract,
                    "preserve_behaviors": step_preserve_behaviors,
                },
            )
            file_changes = step.get("file_changes")
            if isinstance(file_changes, list) and file_changes:
                item.metadata["file_changes"] = [dict(fc) for fc in file_changes if isinstance(fc, dict)]
                item.metadata["change_set"] = {**DEFAULT_CHANGE_SET, **object_to_dict(step.get("change_set")), "change_set_id": str(object_to_dict(step.get("change_set")).get("change_set_id") or f"cs_{item_id}")}
                normalize_plan_item_file_changes(item)
            items.append(item)
            previous_item_id = item_id

        _fix_dangling_depends_on(items, pool_warnings)
        requirement_mapping_normalization = _normalize_requirement_item_mapping(
            requirements=requirements,
            items=items,
        )
        requirement_item_map = _build_requirement_item_map(items)
        plan_quality = _evaluate_plan_contract_quality(
            requirements=requirements,
            items=items,
            requirement_item_map=requirement_item_map,
            automation_level=automation_level,
        )
        metadata = _pool_metadata_from_plan_payload(payload)
        if requirement_mapping_normalization.get("diagnostics"):
            metadata["requirement_mapping_diagnostics"] = list(requirement_mapping_normalization.get("diagnostics") or [])
        if requirement_mapping_normalization.get("request_plan_revision"):
            recovery_decision = dict(requirement_mapping_normalization.get("recovery_decision") or {})
            metadata.update(
                {
                    "plan_revision_required": True,
                    "plan_revision_reason": recovery_decision.get("reason", "ambiguous_requirement_item_mapping"),
                    "patch_generation_recovery_decision": recovery_decision,
                }
            )
            plan_quality = {
                **plan_quality,
                "ok": False,
                "reasons": list(dict.fromkeys([*list(plan_quality.get("reasons") or []), "request_plan_revision:ambiguous_requirement_item_mapping"])),
            }
        metadata.update(
            {
                "original_user_request": original_user_request,
                "selected_architecture": selected_architecture,
                "global_constraints": global_constraints,
                "requirement_trace": requirements,
                "requirement_item_map": requirement_item_map,
                "plan_quality": plan_quality,
                "preserve_behaviors": preserve_behaviors,
            }
        )
        return AtlasPlanPool(
            pool_id=effective_pool_id,
            root_goal=effective_root_goal,
            original_user_request=original_user_request,
            selected_architecture=selected_architecture,
            global_constraints=global_constraints,
            requirements=requirements,
            preserve_behaviors=preserve_behaviors,
            requirement_item_map=requirement_item_map,
            plan_quality=plan_quality,
            project_path=project_path,
            project_name=project_name,
            planning_depth=_normalize_choice(planning_depth, VALID_PLANNING_DEPTHS, "standard"),
            automation_level=_normalize_choice(automation_level, VALID_AUTOMATION_LEVELS, "plan_then_ask"),
            execution_strategy=_normalize_choice(execution_strategy, VALID_EXECUTION_STRATEGIES, "sequential"),
            items=items,
            linked_requirement_id=linked_requirement_id,
            linked_plan_id=linked_plan_id,
            warnings=pool_warnings,
            errors=pool_errors,
            metadata=metadata,
        )

    def build_from_autopilot_plan(
        self,
        autopilot_plan: object | dict,
        root_goal: str = "",
        project_path: str = "",
        project_name: str = "",
        pool_id: str = "",
    ) -> AtlasPlanPool:
        payload = object_to_dict(autopilot_plan)
        tasks = payload.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            return self.build_fallback_pool(
                root_goal=root_goal or str(payload.get("user_goal") or payload.get("interpreted_goal") or ""),
                project_path=project_path or str(payload.get("project_path") or ""),
                project_name=project_name or str(payload.get("project_name") or ""),
                pool_id=pool_id,
            )

        ordered_tasks = self._order_autopilot_tasks(tasks, coerce_list(payload.get("execution_order")))
        effective_pool_id = pool_id or str(payload.get("pool_id") or "") or _new_pool_id()
        effective_root_goal = root_goal or str(payload.get("interpreted_goal") or payload.get("user_goal") or "")
        linked_autopilot_id = str(payload.get("autopilot_id") or "")
        items: list[AtlasPlanItem] = []

        for index, raw_task in enumerate(ordered_tasks, start=1):
            task = object_to_dict(raw_task)
            item_id = str(task.get("task_id") or task.get("item_id") or _generated_item_id(index))
            title = str(task.get("title") or f"Autopilot task {index}")
            description = str(task.get("description") or "")
            risk_level = normalize_risk_level(task.get("risk_level"))
            task_type = str(task.get("task_type") or "").strip().lower()
            item_type = task_type if task_type in VALID_ITEM_TYPES else infer_item_type(task_type, title, description)
            status = self._map_autopilot_status(task.get("status"))
            linked_requirement_id = str(task.get("linked_requirement_id") or payload.get("linked_requirement_id") or "")
            linked_plan_id = str(task.get("linked_plan_id") or payload.get("linked_plan_id") or "")
            item = AtlasPlanItem(
                item_id=item_id,
                pool_id=effective_pool_id,
                title=title,
                goal=str(task.get("goal") or description or title),
                parent_plan_id=linked_plan_id,
                description=description,
                item_type=item_type,
                status=status,
                priority=normalize_priority(task.get("priority")),
                risk_level=risk_level,
                depends_on=coerce_list(task.get("depends_on")),
                target_files=coerce_list(task.get("target_files")),
                done_definition=coerce_list(task.get("acceptance_criteria") or payload.get("done_definition")),
                requires_user_confirmation=risk_level in {"high", "critical"},
                auto_execution_allowed=risk_level == "low",
                linked_requirement_id=linked_requirement_id,
                linked_plan_id=linked_plan_id,
                linked_run_id=str(task.get("linked_run_id") or payload.get("linked_run_id") or ""),
                metadata={
                    "task_type": task.get("task_type") or "",
                    "target_areas": coerce_list(task.get("target_areas")),
                    "original_task_index": index - 1,
                    "original_task_payload": _compact_payload_summary(task),
                },
            )
            file_changes = task.get("file_changes")
            if isinstance(file_changes, list) and file_changes:
                item.metadata["file_changes"] = [dict(fc) for fc in file_changes if isinstance(fc, dict)]
                item.metadata["change_set"] = {**DEFAULT_CHANGE_SET, **object_to_dict(task.get("change_set")), "change_set_id": str(object_to_dict(task.get("change_set")).get("change_set_id") or f"cs_{item_id}")}
                normalize_plan_item_file_changes(item)
            items.append(item)

        autopilot_warnings = coerce_list(payload.get("warnings"))
        _fix_dangling_depends_on(items, autopilot_warnings)
        return AtlasPlanPool(
            pool_id=effective_pool_id,
            root_goal=effective_root_goal,
            project_path=project_path or str(payload.get("project_path") or ""),
            project_name=project_name or str(payload.get("project_name") or ""),
            # Carry the automation level from the payload so a full-automation run yields a pool
            # tagged "full_autopilot"; the single-item pipeline reads this to relax its policy gate
            # (atlas_full_auto_gate). Defaults preserve the prior "plan_then_ask" behaviour.
            automation_level=_normalize_choice(payload.get("automation_level"), VALID_AUTOMATION_LEVELS, "plan_then_ask"),
            items=items,
            linked_autopilot_id=linked_autopilot_id,
            warnings=autopilot_warnings,
            errors=coerce_list(payload.get("errors")),
            metadata={
                "autopilot_id": linked_autopilot_id,
                "preview_only": payload.get("preview_only", True),
                "assumptions": coerce_list(payload.get("assumptions")),
                "risks": coerce_list(payload.get("risks")),
                "safety_constraints": coerce_list(payload.get("safety_constraints")),
                "selected_architecture_summary": payload.get("selected_architecture_summary") or "",
                "task_decomposition_strategy": payload.get("task_decomposition_strategy") or "",
                "execution_order": coerce_list(payload.get("execution_order")),
            },
        )

    def build_fallback_pool(
        self,
        root_goal: str,
        project_path: str = "",
        project_name: str = "",
        planning_depth: str = "standard",
        automation_level: str = "plan_then_ask",
        execution_strategy: str = "sequential",
        pool_id: str = "",
        warnings: list[str] | None = None,
    ) -> AtlasPlanPool:
        effective_pool_id = pool_id or _new_pool_id()
        pool_warnings = list(warnings or [])
        if "planner_failure_requires_replan" not in pool_warnings:
            pool_warnings.append("planner_failure_requires_replan")
        return AtlasPlanPool(
            pool_id=effective_pool_id,
            root_goal=root_goal,
            original_user_request=root_goal,
            project_path=project_path,
            project_name=project_name,
            planning_depth=_normalize_choice(planning_depth, VALID_PLANNING_DEPTHS, "standard"),
            automation_level=_normalize_choice(automation_level, VALID_AUTOMATION_LEVELS, "plan_then_ask"),
            execution_strategy=_normalize_choice(execution_strategy, VALID_EXECUTION_STRATEGIES, "sequential"),
            status="needs_revision",
            items=[],
            warnings=pool_warnings,
            errors=list(dict.fromkeys([*pool_warnings])),
            plan_quality={"ok": False, "reasons": ["planner_failure_requires_replan"]},
            metadata={
                "fallback_plan_items_generated": False,
                "planner_failure_requires_replan": True,
                "patch_generation_allowed": False,
                "plan_quality": {"ok": False, "reasons": ["planner_failure_requires_replan"]},
            },
        )

    @staticmethod
    def _order_autopilot_tasks(tasks: list[Any], execution_order: list[str]) -> list[Any]:
        if not execution_order:
            return tasks
        task_by_id = {str(object_to_dict(task).get("task_id") or ""): task for task in tasks}
        ordered = [task_by_id[task_id] for task_id in execution_order if task_id in task_by_id]
        ordered_ids = set(execution_order)
        ordered.extend(task for task in tasks if str(object_to_dict(task).get("task_id") or "") not in ordered_ids)
        return ordered

    @staticmethod
    def _map_autopilot_status(status: Any) -> str:
        candidate = str(status or "").strip().lower()
        if candidate == "blocked":
            return "blocked"
        if candidate == "failed":
            return "failed"
        return "queued"
