"""Portal evidence ingestion (PFG-28).

Turns a Portal run outcome (preview/log runtime result + the user's save/discard/snapshot
decision) into model-profile observations, with one hard rule:

- A measured runtime result (pass/fail) is STRONG evidence and moves the model's score
  (a runtime failure lowers it).
- A user decision on its own — discard, save, snapshot — is WEAK feedback. Without a
  runtime result it is recorded for context but never moves the score, so a user discard
  alone does not prove model failure.

Evidence is attributed to the model named in the Portal run's Forge trace.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.schema import ForgeModel, ModelProfile


class EvidenceStrength(StrEnum):
    STRONG_RUNTIME = "strong_runtime"
    WEAK_FEEDBACK = "weak_feedback"
    NONE = "none"


class PortalRunEvidence(ForgeModel):
    installation_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    # Profile dimension this run informs (e.g. web_app, game_canvas, repair).
    dimension: str = "web_app"
    # Measured runtime outcome from preview/log. None => not observed (no strong signal).
    runtime_passed: bool | None = None
    # save_and_exit | save_as_snapshot | discard_and_exit | return_to_app | "" .
    user_decision: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class PortalEvidenceResult(ForgeModel):
    strength: EvidenceStrength
    moved_score: bool
    profile: ModelProfile | None = None
    detail: str = ""


def ingest_portal_evidence(store: ProfileStore, ev: PortalRunEvidence) -> PortalEvidenceResult:
    refs = list(ev.evidence_refs) + [f"portal:{ev.installation_id}"]

    if ev.runtime_passed is not None:
        # Strong, measured runtime signal: this moves the score.
        score = 1.0 if ev.runtime_passed else 0.0
        profile = store.record_observation(
            model_id=ev.model_id, provider_id=ev.provider_id,
            dimensions={ev.dimension: score, "overall": score},
            source="portal_run", evidence_refs=refs,
        )
        # The user decision is still recorded as weak context, but the runtime result
        # already set the score.
        if ev.user_decision:
            profile = store.record_user_feedback(
                model_id=ev.model_id, provider_id=ev.provider_id,
                decision=ev.user_decision, evidence_refs=refs,
            )
        return PortalEvidenceResult(
            strength=EvidenceStrength.STRONG_RUNTIME, moved_score=True, profile=profile,
            detail=f"runtime_{'passed' if ev.runtime_passed else 'failed'}",
        )

    if ev.user_decision:
        # Weak feedback only: a user decision without runtime evidence does not prove
        # anything about the model and must not move the score.
        profile = store.record_user_feedback(
            model_id=ev.model_id, provider_id=ev.provider_id,
            decision=ev.user_decision, evidence_refs=refs,
        )
        return PortalEvidenceResult(
            strength=EvidenceStrength.WEAK_FEEDBACK, moved_score=False, profile=profile,
            detail=f"user_decision:{ev.user_decision}_no_runtime_evidence",
        )

    return PortalEvidenceResult(strength=EvidenceStrength.NONE, moved_score=False,
                                detail="no_evidence")


__all__ = [
    "EvidenceStrength",
    "PortalRunEvidence",
    "PortalEvidenceResult",
    "ingest_portal_evidence",
]
