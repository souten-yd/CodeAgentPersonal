"""TwinBrief compiler.

Transforms Project Intelligence planning/generation packages into a compact,
model-facing TwinBrief.  The compiler is intentionally conservative: it turns
Project Intelligence context into constraints and advisory context, but it does
not execute, apply, verify, or publish anything.
"""
from __future__ import annotations

from hashlib import sha1
from typing import Iterable

from agent.project_intelligence.contracts import GenerationContextPackage, PlanningContextPackage
from agent.twin_control_plane.contracts import TwinBrief, TwinConstraint, default_hard_constraints


def _stable_id(parts: Iterable[str]) -> str:
    data = "|".join(p for p in parts if p)
    return "twinbrief_" + sha1(data.encode("utf-8")).hexdigest()[:12]


def compile_generation_twin_brief(
    package: GenerationContextPackage,
    *,
    goal: str = "",
    mode: str = "existing_project",
) -> TwinBrief:
    """Compile a GenerationContextPackage into a TwinBrief.

    Existing Project Intelligence already supplies target files, actual symbols,
    required interfaces, behavior paths, preserve behaviors, convergence gaps,
    verification requirements, and prohibited divergences.  This function keeps
    those sources authoritative and only reshapes them for instruction
    compilation.
    """
    allowed_refs = [ctx.ref for ctx in package.target_files]
    source_refs = [ctx.path for ctx in package.target_files]
    required_interfaces = [iface.ref for iface in package.required_interfaces]
    impacted_refs = [symbol.ref for symbol in package.actual_symbols]
    impacted_refs.extend(path.path_id for path in package.behavior_paths)
    required_tests = [req.requirement_id for req in package.verification_requirements]
    proof_requirements = [req.description or req.requirement_id for req in package.verification_requirements]
    contracts = list(package.preserve_behaviors)
    contracts.extend(package.prohibited_divergences)

    hard_constraints = default_hard_constraints()
    for ref in package.prohibited_divergences:
        hard_constraints.append(
            TwinConstraint(
                constraint_id=f"preserve:{ref}",
                text=f"Preserve existing behavior or contract: {ref}",
                refs=[ref],
            )
        )

    advisory = []
    for gap in package.convergence_gaps:
        advisory.append(f"convergence_gap:{gap.gap_id}:{gap.description}")
    for src in package.target_files:
        advisory.append(f"source_context:{src.path}:{src.ref}")

    return TwinBrief(
        brief_id=_stable_id([package.plan_pool_id, package.plan_item_id, package.actual_twin_revision_id or ""]),
        goal=goal,
        mode=mode,
        actual_twin_revision_id=package.actual_twin_revision_id,
        blueprint_revision_id=package.blueprint_revision_id,
        allowed_refs=allowed_refs,
        forbidden_refs=[],
        hard_constraints=hard_constraints,
        advisory_context=advisory,
        contracts_to_preserve=sorted(set(contracts)),
        required_interfaces=sorted(set(required_interfaces)),
        impacted_refs=sorted(set(impacted_refs)),
        required_tests=sorted(set(required_tests)),
        proof_requirements=[p for p in proof_requirements if p],
        source_refs=source_refs,
        metadata={
            "plan_pool_id": package.plan_pool_id,
            "plan_item_id": package.plan_item_id,
            "context_manifest_id": package.context_manifest.manifest_id,
            "rollout_mode": package.context_manifest.rollout_mode,
        },
    )


def compile_planning_twin_brief(
    package: PlanningContextPackage,
    *,
    goal: str = "",
    mode: str | None = None,
) -> TwinBrief:
    """Compile a PlanningContextPackage into a task-level TwinBrief."""
    impacted_refs = []
    required_tests = []
    advisory = []
    for item in package.impacted_areas:
        impacted_refs.append(item.ref)
        impacted_refs.extend(item.impacted_refs)
        required_tests.extend(item.recommended_tests)
        advisory.append(f"impact:{item.ref}:confidence={item.confidence}")
    for test in package.relevant_tests:
        required_tests.append(test.ref)
    for gap in package.unresolved_gaps:
        advisory.append(f"gap:{gap.gap_id}:{gap.description}")

    return TwinBrief(
        brief_id=_stable_id([package.context_manifest.manifest_id, package.actual_twin_revision_id or "planning"]),
        goal=goal,
        mode=mode or str(package.project_mode.value),
        actual_twin_revision_id=package.actual_twin_revision_id,
        blueprint_revision_id=package.blueprint_revision_id,
        hard_constraints=default_hard_constraints(),
        advisory_context=advisory,
        impacted_refs=sorted(set(impacted_refs)),
        required_tests=sorted(set(required_tests)),
        proof_requirements=[req.text for req in package.requirements if req.text],
        metadata={
            "context_manifest_id": package.context_manifest.manifest_id,
            "rollout_mode": package.context_manifest.rollout_mode,
            "convergence_report_id": package.convergence_report_id or "",
        },
    )
