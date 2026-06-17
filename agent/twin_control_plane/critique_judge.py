"""Weak-LLM judgment with a critical second opinion — not a single shot.

A one-shot weak-model classification is easy to get wrong. This takes the judgment in TWO passes and
then reconciles DETERMINISTICALLY, so the model's role is bounded and the final decision has an anchor:

1. propose  — the local model classifies the failure (``failure_judge.judge_failure_with_llm``).
2. critique — the model is shown its own proposal and asked for the STRONGEST argument that it is wrong
   and an ALTERNATIVE category (別観点 / 批判的意見). This is an adversarial second viewpoint.
3. reconcile — combine proposal, critique and the DETERMINISTIC prior with no further model call:
   agreement -> high confidence; disagreement -> the candidate matching the deterministic prior wins
   (a tie-break the model cannot skew); if neither matches the prior, fall back to the prior and mark
   the result CONTESTED (low confidence) so the caller knows it is genuinely unsettled.

Two model calls, deterministic reconciliation, never raises — falls back to the deterministic label.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from agent.twin_control_plane.failure_classifier import (
    ENVIRONMENT, GENUINELY_BROKEN, SNAPSHOT_DRIFT, TEST_DEBT, classify_failure_reason,
)
from agent.twin_control_plane.failure_judge import judge_failure_with_llm

_VALID = {ENVIRONMENT, SNAPSHOT_DRIFT, TEST_DEBT, GENUINELY_BROKEN}

_CRITIC_SYSTEM = "You are a skeptical reviewer of a test-failure classification. Return one JSON object."

_CRITIC_INSTRUCTION = (
    "A first reviewer classified a failing test as '{proposed}'. Challenge it: give the STRONGEST "
    "argument this category is wrong, and the single most likely alternative from "
    "[environment, snapshot_drift, test_debt, genuinely_broken]. If the original is clearly right, say "
    "so.\nReturn {{\"agree\": <true|false>, \"alternative\": \"<one category>\", \"why\": \"<short>\"}}."
)


@dataclass
class JudgeResult:
    category: str
    confidence: float            # 0..1 — high on consensus, low when contested
    consensus: bool              # proposal and critique agree
    contested: bool = False      # proposal, critique and prior all disagree -> genuinely unsettled
    proposal: str = ""
    alternative: str = ""
    prior: str = ""
    rationale: str = ""
    perspectives: list[str] = field(default_factory=list)


def judge_failure_with_critique(llm_json_fn: Callable[[str, str], dict | None], reason: str, *,
                                test_id: str = "", code_excerpt: str = "") -> JudgeResult:
    """Two-pass weak-LLM judgment with a critical second opinion, reconciled against the deterministic
    prior. Falls back to the deterministic label on any model problem."""
    prior = classify_failure_reason(reason)
    try:
        proposal = judge_failure_with_llm(llm_json_fn, reason, test_id=test_id, code_excerpt=code_excerpt)
    except Exception:
        proposal = prior

    # 2. critique — adversarial second viewpoint on the proposal.
    alternative = ""
    agree = True
    try:
        user = json.dumps({
            "task": _CRITIC_INSTRUCTION.format(proposed=proposal),
            "test_id": test_id,
            "failure_reason": str(reason)[:500],
            "code_excerpt": str(code_excerpt)[:1500],
            "proposed_category": proposal,
        }, ensure_ascii=False)
        out = llm_json_fn(_CRITIC_SYSTEM, user) or {}
        agree = bool(out.get("agree", True))
        alt = str(out.get("alternative") or "").strip().lower()
        alternative = alt if alt in _VALID else ""
    except Exception:
        agree, alternative = True, ""

    perspectives = ["propose", "critique", "prior"]

    # 3. reconcile — deterministic, no further model call.
    if agree or not alternative or alternative == proposal:
        # the critic upheld the proposal (or gave no usable alternative) -> consensus.
        conf = 0.9 if proposal == prior else 0.75
        return JudgeResult(proposal, conf, consensus=True, proposal=proposal, alternative=alternative,
                           prior=prior, perspectives=perspectives,
                           rationale="proposal upheld by the critique" +
                                     ("" if proposal == prior else " (deterministic prior differs)"))

    # the critic dissents with a real alternative -> tie-break with the deterministic prior.
    if proposal == prior:
        return JudgeResult(proposal, 0.6, consensus=False, proposal=proposal, alternative=alternative,
                           prior=prior, perspectives=perspectives,
                           rationale="critique dissents but proposal matches the deterministic prior")
    if alternative == prior:
        return JudgeResult(alternative, 0.6, consensus=False, proposal=proposal, alternative=alternative,
                           prior=prior, perspectives=perspectives,
                           rationale="critique's alternative matches the deterministic prior; switched")
    # nobody matches the prior — genuinely contested; anchor on the deterministic label.
    return JudgeResult(prior, 0.4, consensus=False, contested=True, proposal=proposal,
                       alternative=alternative, prior=prior, perspectives=perspectives,
                       rationale="proposal, critique and prior all disagree; anchored on deterministic prior")
