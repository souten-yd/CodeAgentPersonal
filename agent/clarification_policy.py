from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClarificationDecision:
    decision: str
    reason: str


class ClarificationPolicy:
    def classify(self, *, user_input: str, task_type: str, requirement_mode: str, project_context: str = "") -> ClarificationDecision:
        mode = (requirement_mode or "").strip().lower()
        text = (user_input or "").strip().lower()
        context = (project_context or "").strip().lower()
        if mode in {"auto", "no_clarification"}:
            return ClarificationDecision("not_needed", "mode_suppressed")
        if len(text) < 24 and task_type in {"bugfix", "ui"}:
            return ClarificationDecision("not_needed", "short_small_task")
        required_keywords = ["新規", "project", "生成", "simulator", "設計", "実装", "architecture", "公開", "認証", "security"]
        if any(k.lower() in text for k in required_keywords) or "ios" in context or "iphone safari" in context:
            return ClarificationDecision("required", "deterministic_keyword_gate")
        ambiguous = ["適当に", "いい感じ", "somehow", "whatever", "いいように"]
        if any(k in text for k in ambiguous):
            return ClarificationDecision("optional", "ambiguity_detected")
        return ClarificationDecision("not_needed", "default_not_needed")
