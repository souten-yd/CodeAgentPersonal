"""H3: Full-axis frontier verification.

Enumerates every benchmark dimension that can be evaluated live (method-backed +
semantic non-method), and pairs the weak-LLM/mechanical results with a frontier judge
via the PR21 harness. After H1/H2 the previously format-only anchor check is semantic,
so the frontier should now confirm anchor_selection_quality instead of flagging it as an
over_claim.

The frontier verdict remains advisory: it never upgrades a weak-LLM result.
"""
from __future__ import annotations

from pathlib import Path

from agent.model_forge.eval_packs import CaseResult
from agent.model_forge.frontier_verification import FrontierJudge, FrontierVerificationHarness
from agent.model_forge.live_capability_eval import LIVE_CAPABILITY_DIMENSIONS
from agent.model_forge.real_method_runner import _METHOD_BY_DIMENSION


def all_live_dimensions() -> list[str]:
    """Every dimension with a live evaluator: method-backed + semantic non-method."""
    return sorted(set(_METHOD_BY_DIMENSION) | set(LIVE_CAPABILITY_DIMENSIONS))


class FullAxisFrontierVerifier:
    """Run frontier verification across all live dimensions of one evaluation run."""

    def __init__(self, evidence_dir: str | Path, *, judge: FrontierJudge | None = None) -> None:
        self._harness = FrontierVerificationHarness(evidence_dir, judge=judge)

    def verify(
        self,
        *,
        run_id: str,
        provider_id: str,
        model_id: str,
        results: list[CaseResult] | list[dict],
        raw_by_case: dict[str, str] | None = None,
    ) -> dict:
        normalized = [r if isinstance(r, dict) else r.model_dump(mode="json") for r in results]
        report = self._harness.verify(
            run_id=run_id,
            provider_id=provider_id,
            model_id=model_id,
            results=normalized,
            raw_by_case=raw_by_case,
        )
        covered = {f"{v['dimension']}" for v in report["verdicts"]}
        report["covered_dimensions"] = sorted(covered)
        report["all_live_dimensions"] = all_live_dimensions()
        report["uncovered_live_dimensions"] = [d for d in all_live_dimensions() if d not in covered]
        return report


__all__ = ["all_live_dimensions", "FullAxisFrontierVerifier"]
