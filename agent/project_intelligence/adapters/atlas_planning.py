"""Atlas planner bridge (PI-17).

Bridges the real Atlas planner to ``ProjectIntelligenceModule.prepare_planning_context``
through the composition-root coordinator. Honours the rollout:

- off: the planner uses the legacy context only (Intelligence is not consulted as input);
- shadow: Intelligence is computed and telemetry recorded, but the planner input is the
  unchanged legacy context;
- active: the planner receives a manifest-backed Intelligence context, with readiness and
  staleness explicit.

The bridge holds only the coordinator (which exposes facades, never stores), so the planner
never accesses module stores directly (ADR-PI-015).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.project_intelligence.contracts import PlanningContextRequest
from agent.project_intelligence.coordinator import ProjectIntelligenceCoordinator

_READY = "ready"


@dataclass
class PlannerContextResult:
    mode: str
    used_intelligence: bool
    context: dict[str, Any]
    readiness: str
    stale: bool
    manifest_id: str | None = None
    shadow_artifact: dict[str, Any] | None = None
    diagnostics: list[str] = field(default_factory=list)


class AtlasPlannerBridge:
    """Production bridge from the Atlas planner to the Project Intelligence facade."""

    def __init__(self, coordinator: ProjectIntelligenceCoordinator) -> None:
        self._coordinator = coordinator

    def build_planner_context(
        self,
        *,
        legacy_context: dict[str, Any],
        request: PlanningContextRequest,
    ) -> PlannerContextResult:
        mode = self._coordinator.rollout.mode_for_phase("planning")
        # Always call the facade so shadow telemetry is recorded; never touch stores.
        pkg = self._coordinator.prepare_planning_context(request)
        readiness = pkg.project_state.readiness
        stale = readiness != _READY
        manifest_id = pkg.context_manifest.manifest_id
        diagnostics = [f"planning rollout mode={mode}", f"twin readiness={readiness}"]

        if mode == "active":
            context = self._intelligence_context(pkg, legacy_context)
            return PlannerContextResult(mode=mode, used_intelligence=True, context=context,
                                        readiness=readiness, stale=stale, manifest_id=manifest_id,
                                        diagnostics=diagnostics)
        if mode == "shadow":
            # Planner input is unchanged; the Intelligence package is a side artifact only.
            return PlannerContextResult(
                mode=mode, used_intelligence=False, context=dict(legacy_context),
                readiness=readiness, stale=stale, manifest_id=manifest_id,
                shadow_artifact={"manifest_id": manifest_id, "phase": pkg.context_manifest.phase,
                                 "impacted_count": len(pkg.impacted_areas)},
                diagnostics=diagnostics,
            )
        # off
        return PlannerContextResult(mode="off", used_intelligence=False, context=dict(legacy_context),
                                    readiness=readiness, stale=stale, manifest_id=None,
                                    diagnostics=["planning rollout mode=off; legacy context only"])

    @staticmethod
    def _intelligence_context(pkg, legacy_context: dict[str, Any]) -> dict[str, Any]:
        # Manifest-backed context: legacy as a base, Intelligence sections layered on top.
        return {
            **legacy_context,
            "source": "project_intelligence",
            "manifest_id": pkg.context_manifest.manifest_id,
            "actual_twin_revision_id": pkg.actual_twin_revision_id,
            "project_mode": pkg.project_mode.value,
            "requirements": [r.model_dump() for r in pkg.requirements],
            "impacted_areas": [i.model_dump() for i in pkg.impacted_areas],
            "unresolved_gaps": [g.model_dump() for g in pkg.unresolved_gaps],
            "readiness": pkg.project_state.readiness,
        }
