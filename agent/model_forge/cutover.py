"""Controlled Forge primary cutover (PFG-36).

Promotes ONE stage to Forge-primary (with the legacy executor kept as fallback) only when:

- a shadow comparison exists for the stage and shows no Forge regression, and
- the operator explicitly acknowledges the cutover (no automatic cutover).

A rollback control reverts the stage to shadow (non-live) at any time without an
acknowledgement, so recovery is always one call away. Every cutover/rollback is recorded.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel
from agent.model_forge.shadow import ShadowStore
from agent.model_forge.stage_matrix import StageMatrix
from agent.model_forge.stage_taxonomy import ForgeStage, StageMode


class CutoverRecord(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    stage: ForgeStage
    status: str = "active"  # "active" | "rolled_back"
    mode: StageMode = StageMode.AUTO_SELECT
    forge_primary: bool = False
    legacy_fallback: bool = True
    shadow_winner: str = ""
    shadow_regression: bool = False
    acknowledged_at: str = ""
    rolled_back_at: str = ""


class CutoverController:
    def __init__(
        self,
        stage_matrix: StageMatrix,
        shadow_store: ShadowStore,
        *,
        store_dir: str | Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._matrix = stage_matrix
        self._shadow = shadow_store
        self._dir = Path(store_dir)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _path(self, stage: ForgeStage) -> Path:
        return self._dir / f"{ForgeStage(stage).value}.cutover.json"

    def cutover(self, stage: ForgeStage | str, *, acknowledge: bool = False) -> CutoverRecord:
        stage = ForgeStage(stage)
        comparison = self._shadow.load(stage)
        if comparison is None:
            raise ValueError(f"no_shadow_evidence_for_{stage.value}")
        if comparison.regression:
            raise ValueError(f"shadow_regression_blocks_cutover_for_{stage.value}")
        # Both sides must have produced usable output and Forge must be at least as good.
        if not (comparison.legacy.available and comparison.forge.available):
            raise ValueError(f"shadow_evidence_unavailable_for_{stage.value}")
        if comparison.winner not in ("forge", "tie"):
            raise ValueError(f"forge_not_better_or_equal_for_{stage.value}")
        if not acknowledge:
            raise PermissionError(
                f"cutover of {stage.value} to Forge primary changes production routing; "
                "pass acknowledge=True to confirm (legacy stays as fallback)"
            )
        # Forge becomes primary for this stage; legacy executor remains as fallback.
        self._matrix.set_policy(
            stage, StageMode.AUTO_SELECT, allow_production_routing=True,
            reason="forge_cutover_with_legacy_fallback",
        )
        record = CutoverRecord(
            stage=stage, status="active", mode=StageMode.AUTO_SELECT,
            forge_primary=True, legacy_fallback=True,
            shadow_winner=comparison.winner, shadow_regression=comparison.regression,
            acknowledged_at=self._clock().isoformat(),
        )
        self._save(record)
        return record

    def rollback(self, stage: ForgeStage | str) -> CutoverRecord:
        stage = ForgeStage(stage)
        # Revert to shadow (non-live): no acknowledgement required to recover.
        self._matrix.set_policy(stage, StageMode.SHADOW_SELECT, reason="forge_cutover_rollback")
        existing = self.load(stage)
        record = CutoverRecord(
            stage=stage, status="rolled_back", mode=StageMode.SHADOW_SELECT,
            forge_primary=False, legacy_fallback=True,
            shadow_winner=existing.shadow_winner if existing else "",
            acknowledged_at=existing.acknowledged_at if existing else "",
            rolled_back_at=self._clock().isoformat(),
        )
        self._save(record)
        return record

    def load(self, stage: ForgeStage | str) -> CutoverRecord | None:
        path = self._path(ForgeStage(stage))
        if not path.exists():
            return None
        return CutoverRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_cutovers(self) -> list[CutoverRecord]:
        if not self._dir.exists():
            return []
        return [CutoverRecord.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self._dir.glob("*.cutover.json"))]

    def _save(self, record: CutoverRecord) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(record.stage).write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


__all__ = ["CutoverRecord", "CutoverController"]
