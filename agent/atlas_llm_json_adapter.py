from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest, AtlasLLMJsonResult
from agent.atlas_llm_model_profiles import resolve_structured_mode

logger = logging.getLogger(__name__)


def call_llm_json(
    fn: Callable[[str, str], dict | None] | None,
    system_prompt: str,
    user_prompt: str,
    *,
    json_schema: dict | None = None,
) -> dict | None:
    """Call an llm_json_fn, threading a JSON schema through when the target supports it.

    The historical interface is a plain ``Callable[[str, str], dict | None]`` (used by tests with
    lambdas). Only the real ``AtlasLLMJsonAdapter`` exposes ``generate_json``; for it we pass the
    schema so llama-server can constrain decoding (and we also inject the schema as a prompt hint,
    since a GBNF/grammar constraint alone does not tell the model the field meanings). Any other
    callable falls back to the 2-arg call unchanged — keeping backward compatibility.
    """
    if fn is None:
        return None
    if json_schema and hasattr(fn, "generate_json"):
        req = AtlasLLMJsonRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            schema_hint=json.dumps(json_schema, ensure_ascii=False),
        )
        result = fn.generate_json(req)
        return result.data if result.ok else None
    return fn(system_prompt, user_prompt)


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
                    logger.warning("llm_json_parse_failed backend=backend_fn model=%s raw=%r", model_name, str(raw or "")[:500])
                    return AtlasLLMJsonResult(ok=False, raw_text=str(raw or ""), model=model_name, backend="backend_fn", error="llm_json_parse_failed")
                return AtlasLLMJsonResult(ok=True, data=parsed, raw_text=str(raw) if isinstance(raw, str) else "", model=model_name, backend="backend_fn")

            if not self.base_url:
                return AtlasLLMJsonResult(ok=False, model=model_name, backend="none", error="llm_backend_unavailable", used_fallback=True)

            raw_text = self.call_openai_compatible(request)
            parsed = self.parse_json_response(raw_text)
            structured = bool(request.json_schema or request.grammar)
            if parsed is None:
                logger.warning("llm_json_parse_failed backend=openai_compatible model=%s raw=%r", model_name, raw_text[:500])
                return AtlasLLMJsonResult(ok=False, raw_text=raw_text, model=model_name, backend="openai_compatible", structured=structured, error="llm_json_parse_failed")
            return AtlasLLMJsonResult(ok=True, data=parsed, raw_text=raw_text, model=model_name, backend="openai_compatible", structured=structured)
        except Exception as exc:  # noqa: BLE001
            return AtlasLLMJsonResult(ok=False, model=model_name, error=f"llm_backend_error:{exc}", used_fallback=True)

    def parse_json_response(self, text_or_obj: str | dict | None) -> dict | None:
        if isinstance(text_or_obj, dict):
            return text_or_obj
        text = str(text_or_obj or "").strip()
        if not text:
            return None
        # 1. Direct JSON object.
        obj = self._loads_object(text)
        if obj is not None:
            return obj
        # 2. A labeled ```json fenced block.
        fenced = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
        if fenced:
            obj = self._loads_object(fenced.group(1))
            if obj is not None:
                return obj
        # 3. Strip ANY fences (plain ``` or ```<lang>) and retry whole-body + brace scan.
        unfenced = self._strip_code_fences(text)
        obj = self._loads_object(unfenced)
        if obj is not None:
            return obj
        obj = self.extract_json_object(unfenced)
        if obj is not None:
            return obj
        # 4. Last resort: the model returned a fenced CODE block but no JSON object. Wrap the first
        #    fenced block body as proposed_content so a "write a file" response is still usable.
        code = self._first_fenced_block_body(text)
        if code:
            return {"proposed_content": code}
        return None

    def _loads_object(self, candidate: str) -> dict | None:
        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _strip_code_fences(self, text: str) -> str:
        # Remove a single wrapping ```/```lang ... ``` if present; otherwise return text unchanged.
        m = re.match(r"\s*```[a-zA-Z0-9_-]*\s*\n?([\s\S]*?)\n?```\s*$", text)
        return m.group(1).strip() if m else text

    def _first_fenced_block_body(self, text: str) -> str:
        m = re.search(r"```[a-zA-Z0-9_-]*\s*\n?([\s\S]*?)```", text)
        return m.group(1).strip() if m else ""

    def extract_json_object(self, text: str) -> dict | None:
        # Balanced-brace scan: find the first '{' whose matching '}' yields valid JSON. Tolerant of
        # nested braces and trailing prose where naive find/rfind fails.
        n = len(text)
        for start in range(n):
            if text[start] != "{":
                continue
            depth = 0
            in_str = False
            esc = False
            for end in range(start, n):
                ch = text[end]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        obj = self._loads_object(text[start : end + 1])
                        if obj is not None:
                            return obj
                        break  # this {...} span is not valid JSON; try the next '{'
        return None

    def build_messages(self, request: AtlasLLMJsonRequest) -> list[dict]:
        user_prompt = request.user_prompt
        # Always convey the schema in-prompt when one is present. For models that don't use strict
        # json_schema decoding (e.g. Gemma -> json_object mode), the prompt hint is the ONLY thing that
        # tells the model the field meanings, so fall back to the json_schema if no explicit hint was set.
        hint = request.schema_hint or (json.dumps(request.json_schema, ensure_ascii=False) if request.json_schema else "")
        if hint:
            user_prompt = f"{user_prompt}\n\nJSON schema hint:\n{hint}"
        return [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def call_openai_compatible(self, request: AtlasLLMJsonRequest) -> str:
        # Prefer a structured-output constraint (json_schema / GBNF grammar) so a weak local model
        # cannot emit broken JSON. If the server rejects the param (older llama-server, or a model
        # that does not support it), fall back to plain json_object so we never hard-fail on it.
        try:
            return self._post_chat(request, structured=True)
        except urllib_error.HTTPError as exc:
            if (request.json_schema or request.grammar) and exc.code in (400, 404, 422, 501):
                logger.warning(
                    "structured_output_rejected code=%s; retrying with response_format=json_object", exc.code
                )
                return self._post_chat(request, structured=False)
            raise

    def _post_chat(self, request: AtlasLLMJsonRequest, *, structured: bool) -> str:
        endpoint = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        payload: dict = {
            "model": request.model or self.model or "local-llm",
            "messages": self.build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        # Per-model structured-output mode: a strict json_schema grammar collapses some models
        # (notably Gemma 4), so the preferred mode is resolved from the model id. We still only apply
        # a constraint when the caller asked for structured output (structured=True).
        mode = resolve_structured_mode(request.model or self.model) if structured else "json_object"
        if mode == "json_schema" and request.json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "atlas_output", "schema": request.json_schema, "strict": True},
            }
        elif mode == "grammar" and request.grammar:
            payload["grammar"] = request.grammar
            payload["response_format"] = {"type": "json_object"}
        elif mode == "off":
            pass  # prompt-only; schema is still injected as a prompt hint via build_messages
        else:
            # "json_object" (incl. Gemma default) and any mode whose required input is absent: ask for
            # syntactically valid JSON and rely on the in-prompt schema hint + parser backstop.
            payload["response_format"] = {"type": "json_object"}
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
