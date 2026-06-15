"""Skill Distiller (TFG-10 / Package 9A).

Distill recurring successful patterns from indexed golden patches into compact,
evidence-backed skills that can advise future TwinBrief / Instruction Compiler prompts.

Like Golden Patch Retrieval, distilled skills are advisory:

- a skill is only emitted when a pattern recurs at least ``min_support`` times across
  distinct patches and carries evidence refs;
- each skill records its scope (task category + route) and the supporting patch ids;
- skills never override Project Twin, Contract Sentinel, StateMirror, Schema Guardian,
  or TwinProof findings, and disabling distillation changes no correctness path.
"""
from __future__ import annotations

from pydantic import Field

from agent.model_forge.golden_patch_retrieval import GoldenPatch
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel

DEFAULT_MIN_SUPPORT = 2


class DistilledSkill(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    skill_id: str = Field(min_length=1)
    task_category: str = ""
    route: ForgeRoute | None = None
    # Short guardrail/how-to hint derived from the recurring pattern.
    hint: str = ""
    support: int = 0
    confidence: float = 0.0
    # Always advisory: a distilled skill is an example, never authority.
    advisory: bool = True
    patch_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


def _scope_key(patch: GoldenPatch) -> tuple[str, ForgeRoute | None]:
    return (patch.task_category, patch.route)


def distill_skills(
    patches: list[GoldenPatch], *, enabled: bool = True, min_support: int = DEFAULT_MIN_SUPPORT
) -> list[DistilledSkill]:
    """Group accepted patches by (task_category, route) scope and emit one skill per
    scope that recurs at least ``min_support`` times with evidence.

    ``enabled=False`` returns no skills so distillation can be turned off freely."""
    if not enabled:
        return []
    groups: dict[tuple[str, ForgeRoute | None], list[GoldenPatch]] = {}
    for patch in patches:
        if patch.proof_outcome != "accepted":
            continue  # only successful patches inform a skill
        groups.setdefault(_scope_key(patch), []).append(patch)

    skills: list[DistilledSkill] = []
    for (task_category, route), members in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        support = len(members)
        evidence = sorted({ref for m in members for ref in m.evidence_refs})
        if support < min_support or not evidence:
            # No recurrence or no evidence => not a skill, just isolated history.
            continue
        patch_refs = sorted(m.patch_id for m in members)
        route_label = route.value if route is not None else "any_route"
        skill_id = f"skill:{task_category or 'any'}:{route_label}"
        skills.append(
            DistilledSkill(
                skill_id=skill_id,
                task_category=task_category,
                route=route,
                hint=(
                    f"{support} accepted patches for {task_category or 'any'} via "
                    f"{route_label} passed their proof gates; reuse the same gate "
                    f"discipline as advisory guidance."
                ),
                support=support,
                # Confidence grows with support but stays advisory-capped.
                confidence=round(min(0.9, 0.5 + 0.1 * support), 4),
                patch_refs=patch_refs,
                evidence_refs=evidence,
            )
        )
    return skills


__all__ = ["DEFAULT_MIN_SUPPORT", "DistilledSkill", "distill_skills"]
