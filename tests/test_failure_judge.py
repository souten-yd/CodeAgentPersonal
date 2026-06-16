"""Weak-LLM failure judge: the double-check without a frontier model (deterministic fallback)."""
from __future__ import annotations

from agent.twin_control_plane.failure_judge import judge_failure_with_llm
from agent.twin_control_plane.failure_classifier import ENVIRONMENT, GENUINELY_BROKEN


def test_uses_llm_category_when_valid():
    llm = lambda s, u: {"category": "environment", "why": "crlf"}
    assert judge_failure_with_llm(llm, "assert 'a\r\n' == 'a\n'") == ENVIRONMENT


def test_falls_back_to_deterministic_on_invalid_llm():
    assert judge_failure_with_llm(lambda s, u: {"category": "garbage"},
                                  "FileNotFoundError: x") == ENVIRONMENT  # deterministic prior
    assert judge_failure_with_llm(lambda s, u: None,
                                  "AssertionError: 1 == 2") == GENUINELY_BROKEN


def test_never_raises_on_llm_error():
    def boom(s, u):
        raise RuntimeError("down")
    assert judge_failure_with_llm(boom, "FileNotFoundError: x") == ENVIRONMENT  # falls back, no raise
