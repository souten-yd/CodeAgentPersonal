"""Pilot Context Broker adapters for Planner and patch generation (PDT-5).

These adapters consume the twin only through a `TwinContextPort` (the broker). They never
import or touch the private store, satisfying the dependency rule
`UI/agents -> port, not repository`. When the broker is disabled (or returns an empty
slice) the adapter returns the caller's baseline context unchanged, so current Atlas
behavior is preserved.
"""

from __future__ import annotations

from agent.project_twin.contracts import AtlasPhase, TwinContextRequest, TwinContextSlice


def _render(slice_: TwinContextSlice) -> tuple[str, int]:
    sections = [
        ("Requirements", slice_.requirements),
        ("Symbols", slice_.symbols),
        ("Tests", slice_.tests),
        ("Side effects", slice_.side_effects),
        ("Observations", slice_.observations),
        ("Preserve behaviors", slice_.preserve_behaviors),
        ("Uncertainties", slice_.uncertainties),
    ]
    lines: list[str] = []
    count = 0
    for title, items in sections:
        if not items:
            continue
        lines.append(f"## {title}")
        for it in items:
            lines.append(f"- {it.summary} (conf={it.confidence:.2f}; {it.inclusion_reason})")
            count += 1
    return "\n".join(lines), count


class _BaseContextAdapter:
    phase: AtlasPhase = "planning"

    def __init__(self, context_port) -> None:
        # Only the port is held — never the store.
        self._port = context_port

    def augment(
        self,
        *,
        project_id: str,
        objective: str,
        target_refs: list[str] | None = None,
        plan_pool_id: str | None = None,
        plan_item_id: str | None = None,
        token_budget: int = 4000,
        baseline_context: str = "",
    ) -> dict:
        slice_ = self._port.build_slice(
            TwinContextRequest(
                project_id=project_id,
                objective=objective,
                phase=self.phase,
                plan_pool_id=plan_pool_id,
                plan_item_id=plan_item_id,
                target_refs=target_refs or [],
                token_budget=token_budget,
            )
        )
        rendered, count = _render(slice_)
        if count == 0:
            return {
                "twin_applied": False,
                "context_text": baseline_context,
                "used_tokens": 0,
                "twin_truncated": False,
                "slice": slice_,
            }
        context_text = f"{baseline_context}\n\n# Project Twin context ({self.phase})\n{rendered}".strip()
        return {
            "twin_applied": True,
            "context_text": context_text,
            "used_tokens": slice_.used_tokens,
            "twin_truncated": slice_.truncated,
            "slice": slice_,
        }


class PlannerContextAdapter(_BaseContextAdapter):
    phase: AtlasPhase = "planning"


class PatchContextAdapter(_BaseContextAdapter):
    phase: AtlasPhase = "generation"
