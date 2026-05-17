from __future__ import annotations

import json


class AtlasEvaluatorLLMClient:
    def evaluate(self, prompt: str, metadata: dict) -> str:
        raise NotImplementedError


class AtlasEvaluatorNullLLMClient(AtlasEvaluatorLLMClient):
    def evaluate(self, prompt: str, metadata: dict) -> str:
        return json.dumps({
            "decision": "manual_required",
            "confidence": 0.6,
            "reasons": ["llm_unavailable_using_fallback"],
            "risks": ["requires_manual_review"],
            "recommended_next_actions": ["Review latest verification and safe_apply results manually."],
            "requires_manual_review": True,
            "should_run_debug_review": False,
            "should_generate_patch_proposal": False,
            "should_restore": False,
            "should_continue_autopilot": False,
            "summary": "Fallback client defaulted to manual review."
        })
