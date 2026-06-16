"""Weak-LLM failure judge — the double-check, made KasaneCore-native (no frontier model required).

The deterministic classifier (`failure_classifier`) buckets by reason markers; a frontier review was
then used to catch what the markers missed (CRLF, platform-conditional, UI snapshot drift). To remove
the dependence on a frontier model, this lets the LOCAL weak model perform that judgment: given a
failure reason it picks the same four buckets, with the deterministic result as a prior. The
deterministic rules still handle the bulk; the weak LLM is the second opinion on the residual, so the
"double-check" runs entirely on KasaneCore + the 8080 model.

``llm_json_fn`` is any ``(system, user) -> dict`` (the local adapter). Falls back to the deterministic
label when the model is unavailable or returns junk — never fabricates and never raises.
"""
from __future__ import annotations

import json
from typing import Callable

from agent.twin_control_plane.failure_classifier import (
    ENVIRONMENT, GENUINELY_BROKEN, SNAPSHOT_DRIFT, TEST_DEBT, classify_failure_reason,
)

_VALID = {ENVIRONMENT, SNAPSHOT_DRIFT, TEST_DEBT, GENUINELY_BROKEN}

_SYSTEM = "You classify a failing test. Return a single JSON object only."

_INSTRUCTION = (
    "Classify the pytest failure into exactly one category:\n"
    "- environment: caused by the machine, not the code — missing file/service, a Windows CRLF vs LF "
    "mismatch (\\r\\n vs \\n), cp932 encoding, a refused connection/timeout, a missing browser, or a "
    "platform-conditional assumption (runpod/cuda/cpu/gpu).\n"
    "- snapshot_drift: the test asserts on a rendered UI / HTML / golden snapshot whose source changed; "
    "the TEST's expected value is stale.\n"
    "- test_debt: the test uses a deprecated/removed/renamed API.\n"
    "- genuinely_broken: a real logic regression in the code.\n"
    'Return {"category": "<one of the four>", "why": "<short>"}.'
)


def judge_failure_with_llm(llm_json_fn: Callable[[str, str], dict | None], reason: str, *,
                           test_id: str = "", code_excerpt: str = "") -> str:
    """Weak-LLM bucket for one failure, with the deterministic label as a prior. Returns one of the four
    categories; falls back to the deterministic label on any problem."""
    deterministic = classify_failure_reason(reason)
    try:
        user = json.dumps({
            "task": _INSTRUCTION,
            "test_id": test_id,
            "failure_reason": str(reason)[:500],
            "code_excerpt": str(code_excerpt)[:1500],
            "deterministic_prior": deterministic,
        }, ensure_ascii=False)
        out = llm_json_fn(_SYSTEM, user) or {}
        cat = str(out.get("category") or "").strip().lower()
        return cat if cat in _VALID else deterministic
    except Exception:
        return deterministic
