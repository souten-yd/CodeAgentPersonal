"""Capability scoring bridge (TFG-10 / Package 9).

Turns capability eval-pack outcomes into persisted profile observations, and turns a
persisted ``ModelProfile`` into the ``ModelCapabilityProfile`` that
``ExecutionPolicySelector`` consumes. This is the wire that lets real evaluation
evidence — not hand-set constants — drive Twin injection level, instruction style, and
required gates.

Two boundaries are preserved end-to-end:

- ``unavailable`` is never a pass: a dimension with no evidence is simply absent from
  the profile, so the policy selector falls back to its neutral default for that
  dimension instead of assuming strength;
- only mechanical/evidence-backed case results move a score — there is no weak-feedback
  or LLM-judge path here.
"""
from __future__ import annotations

from collections.abc import Iterable

from agent.model_forge.candidate_evaluator import EvaluatorOutcome
from agent.model_forge.eval_packs import (
    CAPABILITY_DIMENSIONS,
    CapabilityEvalPack,
    CaseResult,
    DimensionScore,
    score_pack,
)
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.schema import ModelProfile

# A dimension at or below this score is reported as a known weakness to the policy
# selector, which raises injection and may add targeted gates.
WEAKNESS_THRESHOLD = 0.55


def _standard_mode():
    # Lazy import to avoid a module-load import cycle with twin_control_plane.contracts.
    from agent.twin_control_plane.contracts import ModelCapabilityMode

    return ModelCapabilityMode.STANDARD


def score_dimensions(
    packs: Iterable[CapabilityEvalPack], results: Iterable[CaseResult]
) -> dict[str, DimensionScore]:
    """Score each supplied pack against the shared pool of case results."""
    pool = list(results)
    return {pack.dimension: score_pack(pack, pool) for pack in packs}


class CapabilityScorer:
    """Record capability eval outcomes into the (append-only, versioned) ProfileStore
    and project the stored profile back into an ExecutionPolicy capability profile."""

    def __init__(self, store: ProfileStore) -> None:
        self._store = store

    def record_pack_result(
        self,
        *,
        model_id: str,
        provider_id: str,
        pack: CapabilityEvalPack,
        results: list[CaseResult],
        source: str = "capability_eval",
    ) -> DimensionScore:
        """Score one pack and persist it as an observation — UNLESS the whole pack was
        unavailable, in which case nothing is recorded (no evidence => no score move)."""
        scored = score_pack(pack, results)
        if scored.outcome == EvaluatorOutcome.UNAVAILABLE or scored.score is None:
            return scored
        self._store.record_observation(
            model_id=model_id,
            provider_id=provider_id,
            dimensions={scored.dimension: scored.score},
            sample_weight=float(scored.sample_count) or 1.0,
            source=source,
            evidence_refs=scored.evidence_refs,
        )
        return scored

    def record_eval_run(
        self,
        *,
        model_id: str,
        provider_id: str,
        packs: Iterable[CapabilityEvalPack],
        results: list[CaseResult],
        source: str = "capability_eval",
    ) -> dict[str, DimensionScore]:
        """Record every pack that produced evidence in a single evaluation run."""
        scored: dict[str, DimensionScore] = {}
        for pack in packs:
            scored[pack.dimension] = self.record_pack_result(
                model_id=model_id, provider_id=provider_id, pack=pack,
                results=results, source=source,
            )
        return scored


def derive_known_weaknesses(
    dimension_scores: dict[str, float], *, threshold: float = WEAKNESS_THRESHOLD
) -> list[str]:
    """Capability dimensions whose evidence-backed score is at or below the threshold.
    Dimensions with no evidence are NOT reported as weaknesses — absence of evidence is
    not evidence of weakness."""
    return sorted(
        dim
        for dim in CAPABILITY_DIMENSIONS
        if dim in dimension_scores and dimension_scores[dim] <= threshold
    )


def build_capability_profile(
    profile: ModelProfile | None,
    *,
    model_id: str = "",
    provider_id: str = "",
    mode: "ModelCapabilityMode | None" = None,
    threshold: float = WEAKNESS_THRESHOLD,
):
    """Project a persisted ModelProfile into the ``ModelCapabilityProfile`` consumed by
    ``ExecutionPolicySelector``.

    Only the capability dimensions are carried over (Forge benchmark dimensions such as
    ``web_app`` are left out so they cannot accidentally drive injection). Known
    weaknesses are derived from evidence-backed scores only."""
    # Imported lazily to avoid a hard import cycle at module load time.
    from agent.model_forge.execution_policy import ModelCapabilityProfile

    if mode is None:
        mode = _standard_mode()
    if profile is None:
        return ModelCapabilityProfile(
            model_id=model_id or "default", provider_id=provider_id, mode=mode,
        )
    capability_scores = {
        dim: float(profile.dimension_scores[dim])
        for dim in CAPABILITY_DIMENSIONS
        if dim in profile.dimension_scores
    }
    return ModelCapabilityProfile(
        model_id=profile.model_id or model_id or "default",
        provider_id=profile.provider_id or provider_id,
        capability_scores=capability_scores,
        known_weaknesses=derive_known_weaknesses(capability_scores, threshold=threshold),
        mode=mode,
        # Carry the injection recommendations so ExecutionPolicySelector can apply them: the
        # twin-assist floor (min help the model needs) and the injection-sweep level interpreted
        # per its objective (min_sufficient -> ceiling; max_score -> floor).
        recommended_twin_injection_level=profile.recommended_twin_injection_level,
        measured_optimal_injection_level=profile.measured_optimal_injection_level,
        injection_objective=profile.injection_objective or "min_sufficient",
    )


def load_capability_profile(
    store: ProfileStore,
    provider_id: str,
    model_id: str,
    *,
    mode: "ModelCapabilityMode | None" = None,
    threshold: float = WEAKNESS_THRESHOLD,
):
    """Convenience: load the latest persisted profile and project it for the selector."""
    profile = store.load_profile(provider_id, model_id)
    return build_capability_profile(
        profile, model_id=model_id, provider_id=provider_id, mode=mode, threshold=threshold,
    )


__all__ = [
    "WEAKNESS_THRESHOLD",
    "CapabilityScorer",
    "score_dimensions",
    "derive_known_weaknesses",
    "build_capability_profile",
    "load_capability_profile",
]
