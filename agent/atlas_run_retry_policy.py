from __future__ import annotations

from dataclasses import dataclass

from agent.atlas_run_schema import AtlasRunState


@dataclass(frozen=True)
class AtlasRunRetryDecision:
    allowed: bool
    reason: str
    mode: str
    next_actions: list[str]


def retry_decision(state: AtlasRunState, *, requested_mode: str = "") -> AtlasRunRetryDecision:
    mode = str(requested_mode or "").strip() or "resume"
    if mode not in {"resume", "rerun"}:
        return AtlasRunRetryDecision(False, "invalid_retry_mode", mode, ["retry", "revise_plan", "cancel"])
    if state.status == "completed" and mode != "rerun":
        return AtlasRunRetryDecision(False, "run_completed", mode, ["rerun"])
    if state.status == "cancelled" and mode != "rerun":
        return AtlasRunRetryDecision(False, "run_cancelled", mode, ["rerun"])
    retry_count = max(0, int(state.retry_count or 0))
    max_retries = max(0, int(state.max_retries or 0))
    if retry_count >= max_retries:
        return AtlasRunRetryDecision(False, "retry_budget_exhausted", mode, ["revise_plan", "cancel"])
    return AtlasRunRetryDecision(True, "rerun_started" if mode == "rerun" else "retry_started", mode, ["wait", "cancel"])
