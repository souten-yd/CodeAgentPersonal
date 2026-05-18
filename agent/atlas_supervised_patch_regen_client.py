from __future__ import annotations

import json


class AtlasPatchRegenLLMClient:
    def generate(self, prompt: str, metadata: dict) -> str:
        raise NotImplementedError


class AtlasPatchRegenNullLLMClient(AtlasPatchRegenLLMClient):
    def __init__(self, canned: str = ""):
        self.canned = canned

    def generate(self, prompt: str, metadata: dict) -> str:
        if self.canned:
            return self.canned
        return json.dumps({"status": "manual_required", "patch": "", "patch_format": "unified_diff", "target_files": metadata.get("target_files", []), "summary": "null_llm_client", "rationale": ["No LLM configured."], "risks": ["manual review required"], "verification_suggestions": [], "manual_review_required": True, "approval_required": True})
