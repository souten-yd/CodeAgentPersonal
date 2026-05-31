"""Diagnose whether a failing verification means the TEST is wrong or the CODE is wrong.

The correction router uses this to route regeneration to the right artifact. Heuristic-first (the
patterns mirror ``debug_loop_runner._classify_root_cause``); the LLM is consulted only for the
genuinely ambiguous case (a plain assertion mismatch, which could be either side). When no LLM is
available the default is ``fix_code`` — an assertion mismatch usually means the code does not yet
satisfy the behaviour the test encodes, and the user's intent is to fix the code. Read-only; never
raises.
"""
from __future__ import annotations

import json
from typing import Callable

FIX_CODE = "fix_code"
FIX_TEST = "fix_test"
AMBIGUOUS = "ambiguous"

_DIAGNOSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["fix_code", "fix_test"]},
        "reason": {"type": "string"},
    },
    "required": ["decision"],
    "additionalProperties": True,
}

_DIAGNOSIS_PROMPT = (
    "You are diagnosing a failing test. You are given the failing test source, the implementation "
    "source it exercises, and the failure output. Decide what to fix: 'fix_code' if the implementation "
    "does not meet the behaviour the test asserts, or 'fix_test' if the test itself is wrong (asserts "
    "the wrong thing, bad setup). Return JSON only: {\"decision\": \"fix_code\"|\"fix_test\", "
    "\"reason\": \"...\"}."
)


class AtlasFailureDiagnosisService:
    def __init__(self, *, llm_json_fn: Callable[[str, str], dict | None] | None = None):
        self.llm_json_fn = llm_json_fn

    def heuristic(self, *, stdout: str = "", stderr: str = "", exit_code=None) -> str:
        body = f"{stdout}\n{stderr}".lower()
        # Code-side signals: the implementation module is broken / missing / has a bad symbol.
        for marker in (
            "modulenotfounderror", "no module named", "importerror",
            "syntaxerror", "invalid syntax", "nameerror", "attributeerror",
        ):
            if marker in body:
                return FIX_CODE
        # Test-side signals: collection failed / no tests / fixture or test-setup error.
        if exit_code == 5 or "no tests ran" in body or "no tests collected" in body:
            return FIX_TEST
        if "errors during collection" in body or ("fixture" in body and "error" in body):
            return FIX_TEST
        # Plain assertion mismatch: could be either side.
        if "assertionerror" in body or "\nassert " in body or body.strip().endswith("assert"):
            return AMBIGUOUS
        return AMBIGUOUS

    def diagnose(self, *, stdout: str = "", stderr: str = "", exit_code=None, test_content: str = "", impl_content: str = "") -> dict:
        decision = self.heuristic(stdout=stdout, stderr=stderr, exit_code=exit_code)
        if decision != AMBIGUOUS:
            return {"decision": decision, "source": "heuristic"}
        if self.llm_json_fn is None:
            return {"decision": FIX_CODE, "source": "default_no_llm"}
        try:
            from agent.atlas_llm_json_adapter import call_llm_json

            payload = {
                "failure_output": f"{stdout}\n{stderr}"[-3000:],
                "test_source": (test_content or "")[:4000],
                "implementation_source": (impl_content or "")[:4000],
            }
            raw = call_llm_json(self.llm_json_fn, _DIAGNOSIS_PROMPT, json.dumps(payload, ensure_ascii=False), json_schema=_DIAGNOSIS_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            return {"decision": FIX_CODE, "source": f"llm_failed:{exc.__class__.__name__}"}
        dec = str((raw or {}).get("decision") or "").lower()
        if dec not in {FIX_CODE, FIX_TEST}:
            return {"decision": FIX_CODE, "source": "llm_unparsed"}
        return {"decision": dec, "source": "llm", "reason": str((raw or {}).get("reason") or "")}
