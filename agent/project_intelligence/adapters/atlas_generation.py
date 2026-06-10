"""Atlas generator and repair bridge (PI-18).

Bridges the Atlas patch-proposal/repair flows to
``ProjectIntelligenceModule.prepare_generation_context`` through the coordinator. It blocks
or requests a refresh when the Actual revision is stale, keeps planned (Blueprint) symbols
clearly separated from real (Actual) symbols so imaginary symbols are never presented as
real, exposes the context manifest for the Proposal to store, and drives repair from actual
failure evidence with a bounded decision (never auto-execution).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.project_intelligence.contracts import (
    GenerationContextRequest,
    RuntimeObservationRecord,
)
from agent.project_intelligence.coordinator import ProjectIntelligenceCoordinator

_BOUNDED_REPAIR_ACTIONS = {
    "repair_current_item", "replan_downstream", "revise_blueprint",
    "request_critical_decision", "halt_unsafe",
}


@dataclass
class GeneratorContextResult:
    mode: str
    used_intelligence: bool
    blocked: bool
    refresh_requested: bool
    context: dict[str, Any]
    manifest_id: str | None
    base_revision: str | None
    diagnostics: list[str] = field(default_factory=list)

    def proposal_metadata(self) -> dict[str, Any]:
        """Metadata the Proposal stores (context manifest + base revision)."""
        return {"context_manifest_id": self.manifest_id, "base_revision": self.base_revision}


@dataclass
class RepairContextResult:
    action: str
    bounded: bool
    failure_evidence_refs: list[str]
    affected_items: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


class AtlasGeneratorBridge:
    def __init__(self, coordinator: ProjectIntelligenceCoordinator) -> None:
        self._coordinator = coordinator

    def build_generation_context(
        self,
        *,
        request: GenerationContextRequest,
        legacy_context: dict[str, Any],
        base_revision: str | None,
        current_actual_revision: str | None,
        current_target_content: dict[str, str] | None = None,
    ) -> GeneratorContextResult:
        mode = self._coordinator.rollout.mode_for_phase("generation")
        pkg = self._coordinator.prepare_generation_context(request)
        manifest_id = pkg.context_manifest.manifest_id

        # Stale Actual revision: the source moved under us -> block + request refresh.
        stale = (current_actual_revision is not None and base_revision is not None
                 and current_actual_revision != base_revision)
        if stale:
            return GeneratorContextResult(
                mode=mode, used_intelligence=(mode == "active"), blocked=True, refresh_requested=True,
                context=dict(legacy_context), manifest_id=manifest_id, base_revision=base_revision,
                diagnostics=[f"stale actual revision: base={base_revision} actual={current_actual_revision};"
                             " refresh before generation"],
            )

        if mode == "off":
            return GeneratorContextResult(mode="off", used_intelligence=False, blocked=False,
                                          refresh_requested=False, context=dict(legacy_context),
                                          manifest_id=None, base_revision=base_revision,
                                          diagnostics=["generation rollout mode=off; legacy context"])
        if mode == "shadow":
            return GeneratorContextResult(mode="shadow", used_intelligence=False, blocked=False,
                                          refresh_requested=False, context=dict(legacy_context),
                                          manifest_id=manifest_id, base_revision=base_revision,
                                          diagnostics=["generation rollout mode=shadow; planner input unchanged"])

        # active: manifest-backed generation context with planned/actual kept distinct.
        context = {
            **legacy_context,
            "source": "project_intelligence",
            "manifest_id": manifest_id,
            "base_revision": base_revision,
            "current_target_content": current_target_content or {},
            # real symbols from the Actual twin (never invented):
            "actual_symbols": [s.model_dump() for s in pkg.actual_symbols],
            # planned Blueprint contracts are clearly labelled as planned, not real:
            "blueprint_contracts": [{**c.model_dump(), "planned": True} for c in pkg.blueprint_contracts],
            "required_interfaces": [i.model_dump() for i in pkg.required_interfaces],
            "behavior_paths": [b.model_dump() for b in pkg.behavior_paths],
            "preserve_behaviors": list(pkg.preserve_behaviors),
            "convergence_gaps": [g.model_dump() for g in pkg.convergence_gaps],
            "verification_requirements": [v.model_dump() for v in pkg.verification_requirements],
            "prohibited_divergences": list(pkg.prohibited_divergences),
        }
        return GeneratorContextResult(mode="active", used_intelligence=True, blocked=False,
                                      refresh_requested=False, context=context, manifest_id=manifest_id,
                                      base_revision=base_revision,
                                      diagnostics=["generation rollout mode=active; manifest-backed"])

    def build_repair_context(
        self,
        *,
        failure_observations: list[RuntimeObservationRecord],
        decision_action: str,
        affected_items: list[str] | None = None,
    ) -> RepairContextResult:
        """Repair uses actual failure evidence and a bounded decision; it never executes."""
        failed = [o for o in failure_observations if o.result == "failed"]
        bounded = decision_action in _BOUNDED_REPAIR_ACTIONS
        diagnostics: list[str] = []
        if not bounded:
            diagnostics.append(f"non-bounded repair action {decision_action!r} rejected")
        if not failed:
            diagnostics.append("no actual failure evidence; repair must be evidence-driven")
        return RepairContextResult(
            action=decision_action if bounded else "halt_unsafe",
            bounded=bounded,
            failure_evidence_refs=[o.observation_id for o in failed],
            affected_items=list(affected_items or []),
            diagnostics=diagnostics,
        )
