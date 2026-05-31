"""Adversarial plan critique: attack a generated plan from several angles before any code is written.

Complements the rule-based PlanReviewer with LLM reasoning. For each angle (security, maintainability,
completeness/missing-steps, requirement alignment) it asks the model to find substantive gaps, then
aggregates the worst-case risk. Schema-constrained via Phase 1. Degrades to an empty critique when no
LLM is available, so planning never hard-depends on it.
"""
from __future__ import annotations

import json
import os
from typing import Callable

from agent.adversarial_plan_critic_schema import AdversarialCritiqueResult, PlanCritiqueFinding
from agent.agent_prompts import ADVERSARIAL_PLAN_CRITIQUE_PROMPT, ADVERSARIAL_PLAN_CRITIQUE_COMBINED_PROMPT
from agent.atlas_llm_json_adapter import call_llm_json

DEFAULT_ANGLES = ["security", "maintainability", "missing_steps", "requirement_alignment"]
_SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "critical": 3}
_RANK_RISK = {0: "low", 1: "medium", 2: "high", 3: "critical"}

_CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "angle": {"type": "string"},
                    "severity": {"type": "string", "enum": ["info", "warning", "high", "critical"]},
                    "category": {"type": "string"},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
                "required": ["severity", "title"],
                "additionalProperties": True,
            },
        },
        "angle_risk": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "requires_revision": {"type": "boolean"},
    },
    "required": ["findings"],
    "additionalProperties": True,
}


def _resolve_mode() -> str:
    """combined (default, 1 LLM call) | per_angle (legacy, one call per angle) | off (skip)."""
    mode = str(os.environ.get("ATLAS_ADVERSARIAL_CRITIQUE_MODE", "combined")).strip().lower()
    return mode if mode in {"combined", "per_angle", "off"} else "combined"


class AdversarialPlanCritic:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None] | None, angles: list[str] | None = None, mode: str | None = None) -> None:
        self.llm_json_fn = llm_json_fn
        self.angles = angles or DEFAULT_ANGLES
        self.mode = (mode or _resolve_mode())

    def critique(self, *, plan_summary: dict, requirement_summary: dict) -> AdversarialCritiqueResult:
        if self.llm_json_fn is None:
            return AdversarialCritiqueResult(warnings=["critique_skipped_no_llm"])
        if self.mode == "off":
            return AdversarialCritiqueResult(warnings=["critique_disabled"])
        if self.mode == "per_angle":
            return self._critique_per_angle(plan_summary=plan_summary, requirement_summary=requirement_summary)
        return self._critique_combined(plan_summary=plan_summary, requirement_summary=requirement_summary)

    def _build_result(self, *, findings_raw, evaluated, warnings, default_angle: str = "other") -> AdversarialCritiqueResult:
        all_findings: list[PlanCritiqueFinding] = []
        worst_rank = 0
        for f in (findings_raw or []):
            if not isinstance(f, dict):
                continue
            sev = str(f.get("severity") or "info").lower()
            if sev not in _SEVERITY_RANK:
                sev = "info"
            worst_rank = max(worst_rank, _SEVERITY_RANK[sev])
            all_findings.append(PlanCritiqueFinding(
                angle=str(f.get("angle") or default_angle),
                severity=sev,
                category=str(f.get("category") or "other"),
                title=str(f.get("title") or ""),
                detail=str(f.get("detail") or ""),
                recommendation=str(f.get("recommendation") or ""),
            ))
        return AdversarialCritiqueResult(
            angles_evaluated=evaluated,
            findings=all_findings,
            consensus_risk=_RANK_RISK.get(worst_rank, "low"),
            requires_revision=worst_rank >= _SEVERITY_RANK["high"],
            warnings=warnings,
        )

    def _critique_combined(self, *, plan_summary: dict, requirement_summary: dict) -> AdversarialCritiqueResult:
        """One LLM call covering every angle. ~4x faster than per-angle on slow local models; each
        finding self-tags its angle so the aggregated result is equivalent in shape."""
        payload = {"angles": self.angles, "plan": plan_summary, "requirement": requirement_summary}
        try:
            raw = call_llm_json(self.llm_json_fn, ADVERSARIAL_PLAN_CRITIQUE_COMBINED_PROMPT, json.dumps(payload, ensure_ascii=False), json_schema=_CRITIQUE_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            return AdversarialCritiqueResult(warnings=[f"critique_failed:combined:{exc.__class__.__name__}"])
        if not isinstance(raw, dict) or not raw:
            return AdversarialCritiqueResult(angles_evaluated=list(self.angles), warnings=["critique_no_output"])
        return self._build_result(findings_raw=raw.get("findings"), evaluated=list(self.angles), warnings=[])

    def _critique_per_angle(self, *, plan_summary: dict, requirement_summary: dict) -> AdversarialCritiqueResult:
        all_findings_raw: list[dict] = []
        warnings: list[str] = []
        evaluated: list[str] = []
        for angle in self.angles:
            payload = {"angle": angle, "plan": plan_summary, "requirement": requirement_summary}
            try:
                raw = call_llm_json(self.llm_json_fn, ADVERSARIAL_PLAN_CRITIQUE_PROMPT, json.dumps(payload, ensure_ascii=False), json_schema=_CRITIQUE_SCHEMA)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"critique_failed:{angle}:{exc.__class__.__name__}")
                continue
            evaluated.append(angle)
            if not isinstance(raw, dict) or not raw:
                continue
            for f in (raw.get("findings") or []):
                if isinstance(f, dict):
                    f.setdefault("angle", angle)
                    all_findings_raw.append(f)
        return self._build_result(findings_raw=all_findings_raw, evaluated=evaluated, warnings=warnings)
