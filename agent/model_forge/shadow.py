"""Stage shadow comparison (PFG-35).

Compares the legacy executor and a Forge candidate for a stage SIDE BY SIDE without any
cutover. Each side's output is scored mechanically via the CandidateEvaluator; the result
records both scores, a winner, and a regression flag. Shadow never changes production
routing: ``promotable`` is False whenever the Forge side regresses or either side's
evidence is unavailable, and shadow results never themselves flip live routing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import Field

from agent.model_forge.candidate_evaluator import (
    CandidateEvaluationInput,
    CandidateEvaluator,
)
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeExecutionResult, ForgeModel
from agent.model_forge.stage_taxonomy import ForgeStage

# Stages eligible for shadow comparison in this package.
SHADOW_STAGES: tuple[ForgeStage, ...] = (
    ForgeStage.PATCH_GENERATION,
    ForgeStage.TEST_GENERATION,
    ForgeStage.FAILURE_CLASSIFICATION,
    ForgeStage.REPAIR,
)


class ShadowSide(ForgeModel):
    label: str  # "legacy" | "forge"
    provider_id: str = ""
    model_id: str = ""
    contract_valid: bool = False
    latency_ms: int = 0
    score: float = 0.0
    available: bool = True
    output_excerpt: str = ""


class ShadowStageComparison(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    stage: ForgeStage
    legacy: ShadowSide
    forge: ShadowSide
    winner: str = ""  # "legacy" | "forge" | "tie" | "unavailable"
    # True when the Forge side is measurably worse than legacy (blocks promotion).
    regression: bool = False
    # Shadow never cuts over: promotable is advisory only and false on regression/unavailable.
    promotable: bool = False
    changes_production_routing: bool = False
    decided_at: str = ""


def _score_side(label: str, result: ForgeExecutionResult, output: str, *,
                evaluator: CandidateEvaluator) -> ShadowSide:
    available = bool(result.errors == [] or result.contract_valid)
    evaluation = evaluator.evaluate(CandidateEvaluationInput(
        candidate_id=f"shadow_{label}_{result.request_id}",
        execution_result=result, output_contract="text", raw_output=output,
    ))
    return ShadowSide(
        label=label, provider_id=result.provider_id, model_id=result.model_id,
        contract_valid=result.contract_valid, latency_ms=result.latency_ms,
        score=evaluation.score.final_score, available=available and bool(output),
        output_excerpt=(output or "")[:200],
    )


def compare_stage(
    stage: ForgeStage,
    *,
    legacy_result: ForgeExecutionResult,
    legacy_output: str,
    forge_result: ForgeExecutionResult,
    forge_output: str,
    clock: Callable[[], datetime] | None = None,
) -> ShadowStageComparison:
    evaluator = CandidateEvaluator()
    legacy = _score_side("legacy", legacy_result, legacy_output, evaluator=evaluator)
    forge = _score_side("forge", forge_result, forge_output, evaluator=evaluator)
    now = (clock or (lambda: datetime.now(timezone.utc)))()

    if not legacy.available or not forge.available:
        winner, regression, promotable = "unavailable", False, False
    elif forge.score > legacy.score:
        winner, regression, promotable = "forge", False, True
    elif forge.score < legacy.score:
        winner, regression, promotable = "legacy", True, False  # regression blocks promotion
    else:
        winner, regression, promotable = "tie", False, False

    return ShadowStageComparison(
        stage=stage, legacy=legacy, forge=forge, winner=winner,
        regression=regression, promotable=promotable, changes_production_routing=False,
        decided_at=now.isoformat(),
    )


class ShadowStore:
    def __init__(self, store_dir: str | Path) -> None:
        self._dir = Path(store_dir)

    def record(self, comparison: ShadowStageComparison) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{comparison.stage.value}.shadow.json"
        path.write_text(
            json.dumps(comparison.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(path)

    def load(self, stage: ForgeStage) -> ShadowStageComparison | None:
        path = self._dir / f"{ForgeStage(stage).value}.shadow.json"
        if not path.exists():
            return None
        return ShadowStageComparison.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "SHADOW_STAGES",
    "ShadowSide",
    "ShadowStageComparison",
    "compare_stage",
    "ShadowStore",
]
