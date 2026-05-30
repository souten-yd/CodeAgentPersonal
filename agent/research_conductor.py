"""Research-first step: survey the codebase before planning so the planner works from grounded evidence.

Mirrors Claude Code's "explore before you plan" behavior, ported to the local LLM. It reuses the
already-collected repository/nexus context (no new file IO) and asks the model to extract concrete,
reusable findings. Schema-constrained via Phase 1's call_llm_json. Degrades to empty findings when no
LLM is available, so planning never hard-depends on it.
"""
from __future__ import annotations

import json
from typing import Callable

from agent.agent_prompts import RESEARCH_FIRST_PROMPT
from agent.atlas_llm_json_adapter import call_llm_json
from agent.research_findings_schema import ResearchFindings

_RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "relevant_files": {"type": "array", "items": {"type": "string"}},
        "existing_patterns": {"type": "array", "items": {"type": "string"}},
        "key_findings": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "recommended_approach": {"type": "string"},
    },
    "required": ["key_findings"],
    "additionalProperties": True,
}


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


class ResearchConductor:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None] | None) -> None:
        self.llm_json_fn = llm_json_fn

    def conduct(self, *, user_input: str, interpreted_goal: str, repository_context: str, nexus_text: str) -> ResearchFindings:
        if self.llm_json_fn is None:
            return ResearchFindings(warnings=["research_skipped_no_llm"])
        payload = {
            "goal": interpreted_goal or user_input,
            "user_input": user_input,
            "repository_context": (repository_context or "")[:9000],
            "nexus_context": (nexus_text or "")[:6000],
        }
        try:
            raw = call_llm_json(self.llm_json_fn, RESEARCH_FIRST_PROMPT, json.dumps(payload, ensure_ascii=False), json_schema=_RESEARCH_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            return ResearchFindings(warnings=[f"research_failed:{exc.__class__.__name__}"])
        if not isinstance(raw, dict) or not raw:
            return ResearchFindings(warnings=["research_no_output"])
        return ResearchFindings(
            relevant_files=_as_str_list(raw.get("relevant_files")),
            existing_patterns=_as_str_list(raw.get("existing_patterns")),
            key_findings=_as_str_list(raw.get("key_findings")),
            risks=_as_str_list(raw.get("risks")),
            open_questions=_as_str_list(raw.get("open_questions")),
            recommended_approach=str(raw.get("recommended_approach") or ""),
        )
