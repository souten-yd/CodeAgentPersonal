from __future__ import annotations

import json
import os
import re
from typing import Callable
from urllib import request as urllib_request

from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest, AtlasLLMJsonResult


class AtlasLLMJsonAdapter:
    def __init__(
        self,
        *,
        backend_fn: Callable[[str, str], str | dict | None] | None = None,
        base_url: str = "",
        model: str = "",
        timeout_seconds: int = 120,
    ) -> None:
        self.backend_fn = backend_fn
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.model = str(model or "").strip()
        self.timeout_seconds = int(timeout_seconds or 120)

    def __call__(self, system_prompt: str, user_prompt: str) -> dict | None:
        result = self.generate_json(AtlasLLMJsonRequest(system_prompt=system_prompt, user_prompt=user_prompt))
        return result.data if result.ok else None

    def generate_json(self, request: AtlasLLMJsonRequest) -> AtlasLLMJsonResult:
        model_name = request.model or self.model
        timeout_seconds = int(request.timeout_seconds or self.timeout_seconds)
        try:
            if self.backend_fn is not None:
                raw = self.backend_fn(request.system_prompt, request.user_prompt)
                parsed = self.parse_json_response(raw)
                if parsed is None:
                    return AtlasLLMJsonResult(ok=False, raw_text=str(raw or ""), model=model_name, backend="backend_fn", error="llm_json_parse_failed")
                return AtlasLLMJsonResult(ok=True, data=parsed, raw_text=str(raw) if isinstance(raw, str) else "", model=model_name, backend="backend_fn")

            if not self.base_url:
                return AtlasLLMJsonResult(ok=False, model=model_name, backend="none", error="llm_backend_unavailable", used_fallback=True)

            raw_text = self.call_openai_compatible(request)
            parsed = self.parse_json_response(raw_text)
            if parsed is None:
                return AtlasLLMJsonResult(ok=False, raw_text=raw_text, model=model_name, backend="openai_compatible", error="llm_json_parse_failed")
            return AtlasLLMJsonResult(ok=True, data=parsed, raw_text=raw_text, model=model_name, backend="openai_compatible")
        except Exception as exc:  # noqa: BLE001
            return AtlasLLMJsonResult(ok=False, model=model_name, error=f"llm_backend_error:{exc}", used_fallback=True)

    def parse_json_response(self, text_or_obj: str | dict | None) -> dict | None:
        if isinstance(text_or_obj, dict):
            return text_or_obj
        text = str(text_or_obj or "").strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None
        except Exception:
            pass

        fenced = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
        if fenced:
            try:
                payload = json.loads(fenced.group(1))
                return payload if isinstance(payload, dict) else None
            except Exception:
                pass

        return self.extract_json_object(text)

    def extract_json_object(self, text: str) -> dict | None:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def build_messages(self, request: AtlasLLMJsonRequest) -> list[dict]:
        user_prompt = request.user_prompt
        if request.schema_hint:
            user_prompt = f"{user_prompt}\n\nJSON schema hint:\n{request.schema_hint}"
        return [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def call_openai_compatible(self, request: AtlasLLMJsonRequest) -> str:
        endpoint = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": request.model or self.model or "local-llm",
            "messages": self.build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib_request.Request(endpoint, data=data, headers=headers, method="POST")
        timeout_sec = int(request.timeout_seconds or self.timeout_seconds)
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") if isinstance(body, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices else {}
        return str(message.get("content") or "")
