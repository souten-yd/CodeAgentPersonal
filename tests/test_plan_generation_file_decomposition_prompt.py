"""Contract: the plan-generation prompt steers file decomposition sensibly.

Root cause context: a Space Invaders run built everything into one large index.html, which a weak
model could not reliably read or edit (it stalled and failed to place new code). Splitting an app
into focused external files makes each step small and the interfaces explicit — but over-splitting
into many tiny files bloats the per-step context just as a giant file does. These assertions pin the
prompt guidance so a regression cannot silently drop either the decomposition default, the
single-file exception, or the context-length balance.
"""
from __future__ import annotations

from agent.agent_prompts import PLAN_GENERATION_PROMPT


def test_prompt_prefers_external_file_decomposition():
    text = PLAN_GENERATION_PROMPT.lower()
    assert "split" in text and "focused files" in text
    # External-reference layout for web apps.
    assert "<script src>" in PLAN_GENERATION_PROMPT
    assert "<link href>" in PLAN_GENERATION_PROMPT
    assert "js/" in PLAN_GENERATION_PROMPT and "css/" in PLAN_GENERATION_PROMPT


def test_prompt_balances_against_context_length():
    # Must warn against over-fragmentation and tie file count to context / app complexity.
    assert "context length" in PLAN_GENERATION_PROMPT.lower()
    assert "over-fragment" in PLAN_GENERATION_PROMPT.lower()
    assert "100-300 lines" in PLAN_GENERATION_PROMPT


def test_prompt_honors_explicit_single_file_request():
    # An explicit single/self-contained request must override the split default.
    lowered = PLAN_GENERATION_PROMPT.lower()
    assert "self-contained" in lowered
    assert "single-file requirement" in lowered or "single file" in lowered
    assert "do not split" in lowered
