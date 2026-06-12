"""Stage Matrix policy and selector (PFG-17).

Per-stage model selection under an explicit, evidence-gated policy. The matrix stores
one StagePolicyEntry per ForgeStage (default disabled or shadow_select) and the selector
turns a policy + candidate pool into a StageSelection that records WHY a model was (or
was not) chosen.

Two hard rules:

- No automatic cutover. Setting a stage to an active production-routing mode
  (fixed_model / auto_select / arena_select) requires an explicit
  ``allow_production_routing=True`` acknowledgement; otherwise the change is refused.
  The selector never promotes a stage on its own.
- Selection reasons are always recorded and serialisable for API/UI.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import Field

from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel
from agent.model_forge.stage_taxonomy import (
    ForgeStage,
    StageMode,
    all_stages,
    changes_production_routing,
    default_stage_mode,
)

# Profile dimension consulted when ranking candidates for a stage.
_STAGE_DIMENSION: dict[ForgeStage, str] = {
    ForgeStage.PLANNING: "planning",
    ForgeStage.PATCH_GENERATION: "patch_generation",
    ForgeStage.TEST_GENERATION: "test_generation",
    ForgeStage.FAILURE_CLASSIFICATION: "failure_classification",
    ForgeStage.REPAIR: "repair",
    ForgeStage.REVIEW: "review",
}


def stage_dimension(stage: ForgeStage | str) -> str:
    return _STAGE_DIMENSION.get(ForgeStage(stage), "overall")


class StageCandidate(ForgeModel):
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


class StagePolicyEntry(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    stage: ForgeStage
    mode: StageMode
    fixed_provider_id: str = ""
    fixed_model_id: str = ""
    fallback_provider_id: str = ""
    fallback_model_id: str = ""
    reason: str = ""
    updated_at: str = ""


class StageSelection(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    stage: ForgeStage
    mode: StageMode
    selected_provider_id: str = ""
    selected_model_id: str = ""
    # True only when the mode is an active production-routing mode AND a model was chosen.
    changes_production_routing: bool = False
    # Legacy executor stays primary whenever Forge does not actively route this stage.
    legacy_remains_primary: bool = True
    candidates_considered: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    decided_at: str = ""


class StageMatrix:
    """Stores per-stage policy entries; defaults to the safe taxonomy default."""

    def __init__(
        self,
        store_path: str | Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = Path(store_path) if store_path else None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._entries: dict[ForgeStage, StagePolicyEntry] = {}
        self._load()

    def _load(self) -> None:
        if self._path and self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for raw in data.get("entries", []):
                entry = StagePolicyEntry.model_validate(raw)
                self._entries[entry.stage] = entry

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": FORGE_SCHEMA_VERSION,
            "entries": [self.get_entry(s).model_dump(mode="json") for s in all_stages()],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_entry(self, stage: ForgeStage | str) -> StagePolicyEntry:
        stage = ForgeStage(stage)
        if stage in self._entries:
            return self._entries[stage]
        return StagePolicyEntry(
            stage=stage, mode=default_stage_mode(stage), reason="taxonomy_default",
        )

    def matrix(self) -> list[StagePolicyEntry]:
        return [self.get_entry(s) for s in all_stages()]

    def set_policy(
        self,
        stage: ForgeStage | str,
        mode: StageMode | str,
        *,
        fixed_provider_id: str = "",
        fixed_model_id: str = "",
        fallback_provider_id: str = "",
        fallback_model_id: str = "",
        reason: str = "",
        allow_production_routing: bool = False,
    ) -> StagePolicyEntry:
        stage = ForgeStage(stage)
        mode = StageMode(mode)
        # No automatic cutover: reaching a live-routing mode is an explicit, acknowledged act.
        if changes_production_routing(mode) and not allow_production_routing:
            raise PermissionError(
                f"stage {stage} -> {mode} changes production routing; "
                "pass allow_production_routing=True to acknowledge cutover"
            )
        entry = StagePolicyEntry(
            stage=stage, mode=mode,
            fixed_provider_id=fixed_provider_id, fixed_model_id=fixed_model_id,
            fallback_provider_id=fallback_provider_id, fallback_model_id=fallback_model_id,
            reason=reason or f"set_to_{mode}",
            updated_at=self._clock().isoformat(),
        )
        self._entries[stage] = entry
        self._save()
        return entry


class StageSelector:
    """Turns a stage policy + candidate pool into a recorded StageSelection."""

    def __init__(
        self,
        matrix: StageMatrix,
        *,
        profile_store: ProfileStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._matrix = matrix
        self._profiles = profile_store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def select(
        self, stage: ForgeStage | str, *, candidates: list[StageCandidate] | None = None
    ) -> StageSelection:
        stage = ForgeStage(stage)
        entry = self._matrix.get_entry(stage)
        candidates = candidates or []
        considered = [f"{c.provider_id}:{c.model_id}" for c in candidates]
        base = StageSelection(
            stage=stage, mode=entry.mode, candidates_considered=considered,
            decided_at=self._clock().isoformat(),
        )

        if entry.mode == StageMode.DISABLED:
            base.reasons = ["stage_disabled", "legacy_primary"]
            return base

        if entry.mode == StageMode.FIXED_MODEL:
            if entry.fixed_model_id:
                base.selected_provider_id = entry.fixed_provider_id
                base.selected_model_id = entry.fixed_model_id
                base.changes_production_routing = True
                base.legacy_remains_primary = False
                base.reasons = ["fixed_model_policy"]
            else:
                base.reasons = ["fixed_model_unset", "legacy_primary"]
            return base

        if entry.mode == StageMode.FALLBACK_ONLY:
            if entry.fallback_model_id:
                base.selected_provider_id = entry.fallback_provider_id
                base.selected_model_id = entry.fallback_model_id
                # Fallback only routes when the primary path is unavailable; on its own
                # it does not change the live default.
                base.reasons = ["fallback_only_policy"]
            else:
                base.reasons = ["fallback_unset", "legacy_primary"]
            return base

        # SHADOW_SELECT / AUTO_SELECT / ARENA_SELECT all rank the candidate pool.
        ranked = self._rank(stage, candidates)
        if not ranked:
            base.reasons = ["no_candidate_available", "legacy_primary"]
            return base
        provider_id, model_id, score, reason = ranked[0]
        base.selected_provider_id = provider_id
        base.selected_model_id = model_id

        if entry.mode == StageMode.SHADOW_SELECT:
            # Shadow observes/compares only; legacy output stays primary.
            base.changes_production_routing = False
            base.legacy_remains_primary = True
            base.reasons = ["shadow_select", reason, "legacy_primary"]
        elif entry.mode == StageMode.ARENA_SELECT:
            # Arena produces candidates; adoption still requires Proposal/Safe Apply.
            base.changes_production_routing = False
            base.legacy_remains_primary = True
            base.reasons = ["arena_select", reason, "candidate_requires_safe_apply"]
        elif entry.mode == StageMode.AUTO_SELECT:
            base.changes_production_routing = True
            base.legacy_remains_primary = False
            base.reasons = ["auto_select", reason]
        return base

    def _rank(
        self, stage: ForgeStage, candidates: list[StageCandidate]
    ) -> list[tuple[str, str, float, str]]:
        dim = stage_dimension(stage)
        scored: list[tuple[str, str, float, str]] = []
        for c in candidates:
            score = 0.0
            reason = "no_profile_default_order"
            if self._profiles is not None:
                profile = self._profiles.load_profile(c.provider_id, c.model_id)
                if profile is not None and dim in profile.dimension_scores:
                    score = profile.dimension_scores[dim]
                    reason = f"profile_{dim}={score}"
            scored.append((c.provider_id, c.model_id, score, reason))
        # Stable sort by score desc; preserves input order for ties / no profiles.
        scored.sort(key=lambda t: t[2], reverse=True)
        return scored


__all__ = [
    "StageCandidate",
    "StagePolicyEntry",
    "StageSelection",
    "StageMatrix",
    "StageSelector",
    "stage_dimension",
]
