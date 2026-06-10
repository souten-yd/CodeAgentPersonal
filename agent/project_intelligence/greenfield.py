"""Greenfield bootstrap orchestrator (PI-20).

A dedicated orchestration mode for empty/near-empty projects that still uses the normal
PlanPool / Proposal / Safe Apply / Verification / Project Intelligence boundaries. It
requires a reviewed, validated, active Blueprint with an exact file manifest and execution
contracts before any broad generation, compiles dependency-ordered PlanItems, and emits one
coherent slice at a time. The orchestrator never writes the workspace itself — every slice is
an apply intent that MUST go through Safe Apply — and its state is serializable so an
interrupted bootstrap resumes safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.architecture_blueprint.contracts import BlueprintRevision
from agent.architecture_blueprint.validator import ValidationReport, validate_blueprint
from agent.project_intelligence.contracts import IntelligenceError, IntelligenceErrorCode
from agent.project_intelligence.plan_compiler import CompiledPlan, PlanItemSpec, compile_plan

_GREENFIELD_MODES = {"empty", "greenfield_partial"}
_ACTIVE_STATES = {"active", "materializing"}


@dataclass
class GreenfieldSession:
    project_id: str
    workspace_id: str
    blueprint_revision_id: str
    project_mode: str
    slices: list[list[str]] = field(default_factory=list)   # ordered layers of item ids
    completed_slices: list[int] = field(default_factory=list)
    items: dict[str, PlanItemSpec] = field(default_factory=dict)

    def to_state(self) -> dict:
        return {
            "project_id": self.project_id, "workspace_id": self.workspace_id,
            "blueprint_revision_id": self.blueprint_revision_id, "project_mode": self.project_mode,
            "slices": self.slices, "completed_slices": self.completed_slices,
            "items": {k: vars(v) for k, v in self.items.items()},
        }

    @classmethod
    def from_state(cls, state: dict) -> "GreenfieldSession":
        items = {k: PlanItemSpec(**v) for k, v in state.get("items", {}).items()}
        return cls(project_id=state["project_id"], workspace_id=state["workspace_id"],
                   blueprint_revision_id=state["blueprint_revision_id"],
                   project_mode=state["project_mode"], slices=state["slices"],
                   completed_slices=state.get("completed_slices", []), items=items)


@dataclass
class SliceWork:
    slice_index: int
    apply_intents: list[PlanItemSpec]
    must_use_safe_apply: bool = True   # the orchestrator never writes the workspace itself


@dataclass
class SliceResult:
    slice_index: int
    refresh_requested: bool = True       # Actual Twin refresh after each apply
    convergence_requested: bool = True   # Convergence after each apply
    next_index: int | None = None


def _layered_slices(plan: CompiledPlan) -> list[list[str]]:
    """Kahn layering: each slice is the set of items whose deps are already satisfied."""
    ids = {i.item_id for i in plan.items}
    deps = {i.item_id: {d for d in i.depends_on if d in ids} for i in plan.items}
    done: set[str] = set()
    layers: list[list[str]] = []
    remaining = set(ids)
    while remaining:
        ready = sorted(i for i in remaining if deps[i] <= done)
        if not ready:  # cycle guard — should not happen for a validated blueprint
            ready = sorted(remaining)
        layers.append(ready)
        done |= set(ready)
        remaining -= set(ready)
    return layers


class GreenfieldOrchestrator:
    """Drives Greenfield bootstrap; emits apply intents, never writes the workspace."""

    def start(self, *, project_id: str, workspace_id: str, project_mode: str,
              blueprint: BlueprintRevision) -> GreenfieldSession:
        if project_mode not in _GREENFIELD_MODES:
            raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_INVALID,
                                    f"greenfield path requires an empty project, got {project_mode!r}")
        # No broad generation without a reviewed, active, validated Blueprint.
        if blueprint.status not in _ACTIVE_STATES:
            raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_INVALID,
                                    f"active Blueprint required before generation (status={blueprint.status!r})")
        report: ValidationReport = validate_blueprint(blueprint)
        if not report.valid:
            raise IntelligenceError(IntelligenceErrorCode.BLUEPRINT_INVALID,
                                    f"blueprint invalid: {[d.code for d in report.diagnostics]}")
        plan: CompiledPlan = compile_plan(blueprint, project_mode=project_mode)
        slices = _layered_slices(plan)
        return GreenfieldSession(
            project_id=project_id, workspace_id=workspace_id,
            blueprint_revision_id=blueprint.revision_id, project_mode=project_mode,
            slices=slices, items={i.item_id: i for i in plan.items},
        )

    def next_slice(self, session: GreenfieldSession) -> SliceWork | None:
        for idx, layer in enumerate(session.slices):
            if idx not in session.completed_slices:
                return SliceWork(slice_index=idx, apply_intents=[session.items[i] for i in layer])
        return None  # all slices complete

    def complete_slice(self, session: GreenfieldSession, slice_index: int, *, applied: bool) -> SliceResult:
        """Record a slice as applied (via Safe Apply) and request refresh + convergence."""
        if not applied:
            return SliceResult(slice_index=slice_index, refresh_requested=False,
                               convergence_requested=False, next_index=slice_index)
        if slice_index not in session.completed_slices:
            session.completed_slices.append(slice_index)
        nxt = self.next_slice(session)
        return SliceResult(slice_index=slice_index, refresh_requested=True,
                           convergence_requested=True,
                           next_index=nxt.slice_index if nxt else None)

    def is_complete(self, session: GreenfieldSession) -> bool:
        return len(session.completed_slices) == len(session.slices)

    # The orchestrator intentionally exposes NO workspace-write method: generation must go
    # through Safe Apply. This flag documents and tests that invariant.
    requires_safe_apply = True
