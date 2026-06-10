"""Project Intelligence compiled-plan to Atlas PlanPool adapter (PIR-10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.atlas_plan_pool_schema import AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.project_intelligence.plan_compiler import (
    CompiledPlan,
    CREATE_FILE,
    CREATE_STRUCTURE,
    MODIFY,
    PLAN_CONTRACT,
    REPAIR_ITEM,
    VERIFY_CONTRACT,
)


def _files_from_refs(refs: list[str]) -> list[str]:
    return [ref.removeprefix("file://") for ref in refs if ref.startswith("file://")]


def _action_for_kind(kind: str) -> str:
    if kind in {CREATE_FILE, CREATE_STRUCTURE}:
        return "create"
    if kind == MODIFY:
        return "update"
    if kind == REPAIR_ITEM:
        return "update"
    if kind == VERIFY_CONTRACT:
        return "test"
    if kind == PLAN_CONTRACT:
        return "inspect"
    return "update"


def compiled_plan_to_plan_payload(plan: CompiledPlan, *, root_goal: str = "") -> dict[str, Any]:
    """Translate a CompiledPlan into the existing AtlasPlanPoolBuilder payload."""
    metadata = {
        **plan.plan_pool_metadata(),
        "source": "project_intelligence_compiled_plan",
        "planning_phase": plan.planning_phase,
    }
    steps: list[dict[str, Any]] = []
    for item in plan.items:
        step_metadata = {
            "blueprint_element_ids": list(item.blueprint_element_ids),
            "planning_envelope_hash": plan.planning_envelope_hash,
            "project_intelligence_refs": plan.plan_pool_metadata(),
        }
        steps.append(
            {
                "step_id": item.item_id,
                "title": item.item_id,
                "description": "; ".join(item.convergence_criteria),
                "goal": "; ".join(item.convergence_criteria) or item.item_id,
                "action_type": _action_for_kind(item.kind),
                "target_files": _files_from_refs(item.target_refs),
                "depends_on": list(item.depends_on),
                "requirement_ids": list(item.requirement_ids),
                "acceptance_criteria": list(item.convergence_criteria),
                "verification_contract": {
                    "blueprint_element_ids": list(item.blueprint_element_ids),
                    "target_refs": list(item.target_refs),
                    "convergence_criteria": list(item.convergence_criteria),
                },
                "metadata": step_metadata,
            }
        )
    return {
        "root_goal": root_goal,
        "plan_id": plan.context_manifest_id or plan.blueprint_revision_id or "",
        "implementation_steps": steps,
        "metadata": metadata,
        "requirements": [
            {"requirement_id": req_id, "description": req_id, "required": True}
            for req_id in sorted({rid for item in plan.items for rid in item.requirement_ids})
        ],
    }


def build_plan_pool_from_compiled_plan(
    plan: CompiledPlan,
    *,
    root_goal: str,
    project_path: str = "",
    project_name: str = "",
    pool_id: str = "",
    builder: AtlasPlanPoolBuilder | None = None,
) -> AtlasPlanPool:
    builder = builder or AtlasPlanPoolBuilder()
    pool = builder.build_from_plan_payload(
        compiled_plan_to_plan_payload(plan, root_goal=root_goal),
        root_goal=root_goal,
        project_path=project_path,
        project_name=project_name,
        pool_id=pool_id,
    )
    for item in pool.items:
        compiled = plan.item(item.item_id)
        if compiled is None:
            continue
        if compiled.status == "completed":
            item.status = compiled.status
        item.metadata = {
            **dict(item.metadata or {}),
            "blueprint_element_ids": list(compiled.blueprint_element_ids),
            "project_intelligence_refs": plan.plan_pool_metadata(),
            "planning_envelope_hash": plan.planning_envelope_hash,
            "compiled_status": compiled.status,
        }
    pool.completed_item_ids = [item.item_id for item in pool.items if item.status == "completed"]
    pool.metadata = {
        **dict(pool.metadata or {}),
        **plan.plan_pool_metadata(),
        "source": "project_intelligence_compiled_plan",
    }
    return pool


def create_authoritative_plan_pool(
    plan: CompiledPlan,
    *,
    storage: AtlasPlanPoolStorage,
    root_goal: str,
    project_path: str = "",
    project_name: str = "",
    pool_id: str = "",
) -> AtlasPlanPool:
    """Build and persist through AtlasPlanPoolStorage, never through private writes."""
    pool = build_plan_pool_from_compiled_plan(
        plan,
        root_goal=root_goal,
        project_path=project_path,
        project_name=project_name,
        pool_id=pool_id,
    )
    storage.save_pool(pool)
    return storage.load_pool(pool.pool_id)


def create_authoritative_plan_pool_at(
    plan: CompiledPlan,
    *,
    ca_data_root: str | Path,
    root_goal: str,
    project_path: str = "",
    project_name: str = "",
    pool_id: str = "",
) -> AtlasPlanPool:
    return create_authoritative_plan_pool(
        plan,
        storage=AtlasPlanPoolStorage(ca_data_root),
        root_goal=root_goal,
        project_path=project_path,
        project_name=project_name,
        pool_id=pool_id,
    )
