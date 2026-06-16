from __future__ import annotations

import json
import copy
import logging
import os
import re
import socket
import time
from datetime import datetime, timezone
from typing import Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest, AtlasLLMJsonResult
from agent.atlas_llm_model_profiles import resolve_structured_mode

logger = logging.getLogger(__name__)

# Appended to the prompt on a one-shot retry after the first response failed to parse. Weak or
# non-enforcing openai-compatible servers occasionally emit invalid JSON on the first attempt;
# re-asking with a hard "valid JSON only" instruction at temperature 0 recovers most of these.
_STRICT_JSON_REINFORCEMENT = (
    "\n\nIMPORTANT: Respond with a SINGLE valid JSON object ONLY. No prose, no markdown, no code "
    "fences, no trailing commas. Ensure every string is closed and every bracket is balanced."
)


class _StreamTimeout(Exception):
    """A streaming planning call exceeded a phase-specific timeout budget.

    ``phase`` is one of the truthful terminal reasons the planner must be able to
    distinguish for a slow local model:

    - ``llm_stalled_before_first_token``: prefill never produced a content token.
    - ``llm_stalled_after_progress``: generation started but then went idle.
    - ``llm_total_timeout``: total wall-clock budget exhausted regardless of progress.

    A slow-but-progressing model resets the idle timer on every real token and so
    must never surface ``llm_stalled_after_progress`` purely for being slow.
    """

    def __init__(self, phase: str, *, tokens_generated: int = 0) -> None:
        super().__init__(phase)
        self.phase = phase
        self.tokens_generated = int(tokens_generated)


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
        on_progress: Callable[[dict], None] | None = None,
        on_usage: Callable[[dict], None] | None = None,
    ) -> None:
        self.backend_fn = backend_fn
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.model = str(model or "").strip()
        self.timeout_seconds = int(timeout_seconds or 120)
        self.on_progress = on_progress
        # Called with the enriched usage dict (prompt/completion/total + thinking/output) after
        # each call, so the caller can accumulate token counts into the run metadata / UI.
        self.on_usage = on_usage
        # Real token usage (prompt_tokens / completion_tokens / total_tokens) captured from
        # the last call's response. Populated when the server reports usage (llama.cpp does,
        # and the streaming path now requests stream_options.include_usage).
        self.last_usage: dict = {}

    def with_progress(self, on_progress: Callable[[dict], None] | None) -> "AtlasLLMJsonAdapter":
        clone = copy.copy(self)
        clone.on_progress = on_progress
        return clone

    def with_usage(self, on_usage: Callable[[dict], None] | None) -> "AtlasLLMJsonAdapter":
        clone = copy.copy(self)
        clone.on_usage = on_usage
        return clone

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
                # One-shot strict retry before giving up, so a single malformed response does not
                # silently drop the result (e.g. an adversarial critique becoming a no-op).
                retry_request = request.model_copy(
                    update={
                        "user_prompt": request.user_prompt + _STRICT_JSON_REINFORCEMENT,
                        "temperature": 0.0,
                    }
                )
                retry_raw = self.call_openai_compatible(retry_request)
                retry_parsed = self.parse_json_response(retry_raw)
                if retry_parsed is not None:
                    return AtlasLLMJsonResult(ok=True, data=retry_parsed, raw_text=retry_raw, model=model_name, backend="openai_compatible", structured=structured, warnings=["llm_json_parse_retry_succeeded"])
                logger.warning("llm_json_parse_failed backend=openai_compatible model=%s raw=%r", model_name, raw_text[:500])
                return AtlasLLMJsonResult(ok=False, raw_text=raw_text, model=model_name, backend="openai_compatible", structured=structured, error="llm_json_parse_failed")
            return AtlasLLMJsonResult(ok=True, data=parsed, raw_text=raw_text, model=model_name, backend="openai_compatible", structured=structured)
        except _StreamTimeout as exc:
            # Phase-specific terminal reason so Plan status/journal can record the timeout phase
            # truthfully (before-first-token vs after-progress vs total) instead of a flat stall.
            return AtlasLLMJsonResult(
                ok=False,
                model=model_name,
                backend="openai_compatible",
                error=exc.phase,
                used_fallback=True,
                metadata={"timeout_phase": exc.phase, "tokens_generated": exc.tokens_generated},
            )
        except socket.timeout:
            return AtlasLLMJsonResult(ok=False, model=model_name, backend="openai_compatible", error="llm_stalled", used_fallback=True)
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
        # 3.5 Best-effort repair of a *truncated* or corrupt-tail object/array (a common weak-model
        #     failure: output cut off at max_tokens, or the model degrading into invalid tokens
        #     partway through). Reconstructs from the OUTERMOST '{' so the wrapper (e.g. the
        #     "findings" array) is preserved, recovering the longest well-formed prefix and closing
        #     open brackets. Runs before extract_json_object, which would otherwise grab the first
        #     inner object and silently drop the wrapper. Only a result that re-parses to a valid
        #     dict is accepted, so no fields are invented — at worst a partial trailing element is
        #     dropped instead of losing the whole payload.
        obj = self._repair_and_load(unfenced)
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

    @staticmethod
    def _needed_closers(fragment: str) -> str:
        """The bracket closers needed to balance a fragment that ends outside any string."""
        stack: list[str] = []
        in_str = False
        esc = False
        for ch in fragment:
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
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]" and stack:
                stack.pop()
        return "".join(reversed(stack))

    def _repair_and_load(self, text: str) -> dict | None:
        start = text.find("{")
        if start == -1:
            return None
        body = text[start:]
        # Candidate cut points are element boundaries: just after a closed string or a closed
        # bracket. Trying the longest first keeps as many complete elements as possible while
        # discarding a half-written / corrupt trailing element.
        cuts: list[int] = []
        in_str = False
        esc = False
        for i, ch in enumerate(body):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                    cuts.append(i + 1)
                continue
            if ch == '"':
                in_str = True
            elif ch in "}]":
                cuts.append(i + 1)
        for cut in sorted(set(cuts), reverse=True)[:128]:
            fragment = body[:cut].rstrip()
            if fragment.endswith(","):
                fragment = fragment[:-1].rstrip()
            candidate = fragment + self._needed_closers(fragment)
            obj = self._loads_object(candidate)
            if isinstance(obj, dict):
                return obj
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
        use_stream = self._streaming_enabled(request)
        try:
            return self._post_chat_stream(request, structured=True) if use_stream else self._post_chat(request, structured=True)
        except urllib_error.HTTPError as exc:
            if (request.json_schema or request.grammar) and exc.code in (400, 404, 422, 501):
                logger.warning(
                    "structured_output_rejected code=%s; retrying with response_format=json_object", exc.code
                )
                return self._post_chat_stream(request, structured=False) if use_stream else self._post_chat(request, structured=False)
            raise

    def _streaming_enabled(self, request: AtlasLLMJsonRequest) -> bool:
        if str(os.environ.get("ATLAS_LLM_STREAMING", "1")).strip() == "0":
            return False
        return bool(request.stream or self.on_progress is not None)

    def _build_payload(self, request: AtlasLLMJsonRequest, *, structured: bool) -> dict:
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
        return payload

    def _build_request(self, payload: dict):
        endpoint = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return urllib_request.Request(endpoint, data=data, headers=headers, method="POST")

    def _post_chat(self, request: AtlasLLMJsonRequest, *, structured: bool) -> str:
        payload = self._build_payload(request, structured=structured)
        req = self._build_request(payload)
        timeout_sec = int(request.timeout_seconds or self.timeout_seconds)
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices") if isinstance(body, dict) else None
        message = choices[0].get("message") if isinstance(choices, list) and choices else {}
        content = str(message.get("content") or "")
        reasoning = str(message.get("reasoning_content") or "") if isinstance(message, dict) else ""
        _thinking, output_text = split_thinking(content)
        if isinstance(body, dict) and isinstance(body.get("usage"), dict):
            self.last_usage = _thinking_split_usage(
                dict(body["usage"]), content_text=content, reasoning_chars=len(reasoning))
            logger.info(
                "llm token usage: prompt=%s thinking=%s output=%s total=%s (model=%s)",
                self.last_usage.get("prompt_tokens"), self.last_usage.get("thinking_tokens"),
                self.last_usage.get("output_tokens"), self.last_usage.get("total_tokens"),
                payload.get("model"))
            self._emit_usage(self.last_usage)
        return output_text

    def _post_chat_stream(self, request: AtlasLLMJsonRequest, *, structured: bool) -> str:
        payload = self._build_payload(request, structured=structured)
        payload["stream"] = True
        # Ask the server to emit a final usage chunk so we can record REAL token counts
        # (prompt + completion), not just the local content-token approximation.
        payload["stream_options"] = {"include_usage": True}
        self.last_usage = {}
        req = self._build_request(payload)
        # Three independent budgets so a slow local model is judged on the right axis:
        #   - first-token: how long prefill may run before any content token;
        #   - idle-token: max gap *between real tokens* once generation has started;
        #   - total: an absolute wall-clock ceiling regardless of progress.
        # New env names take precedence; the historical names remain as fallbacks so existing
        # deployments and tuning keep working.
        first_token_sec = _resolve_timeout("ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS", "ATLAS_PLAN_FIRST_TOKEN_SEC", 300.0)
        idle_token_sec = _resolve_timeout("ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS", "ATLAS_LLM_INTER_TOKEN_SEC", 300.0)
        total_sec = _resolve_timeout("ATLAS_LLM_TOTAL_TIMEOUT_SECONDS", "", 1800.0)
        chunks: list[str] = []
        reasoning_chars = 0  # separate reasoning_content deltas (reasoning models)
        tokens_generated = 0
        saw_token = False
        start_mono = time.monotonic()
        last_token_mono = start_mono
        with urllib_request.urlopen(req, timeout=first_token_sec) as resp:  # noqa: S310
            self._set_response_timeout(resp, first_token_sec)
            try:
                for raw_line in resp:
                    now = time.monotonic()
                    # Wall-clock guards run on every received line, so a server that keeps the
                    # socket alive with heartbeats/keep-alives cannot silently dodge the budgets.
                    if now - start_mono > total_sec:
                        raise _StreamTimeout("llm_total_timeout", tokens_generated=tokens_generated)
                    if not saw_token and now - start_mono > first_token_sec:
                        raise _StreamTimeout("llm_stalled_before_first_token", tokens_generated=tokens_generated)
                    if saw_token and now - last_token_mono > idle_token_sec:
                        raise _StreamTimeout("llm_stalled_after_progress", tokens_generated=tokens_generated)
                    line = raw_line.decode("utf-8", errors="replace").strip() if isinstance(raw_line, bytes) else str(raw_line).strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except Exception:
                        continue
                    # Final usage chunk (stream_options.include_usage): record real token counts.
                    if isinstance(event, dict) and isinstance(event.get("usage"), dict):
                        self.last_usage = dict(event["usage"])
                    choices = event.get("choices") if isinstance(event, dict) else None
                    choice = choices[0] if isinstance(choices, list) and choices else {}
                    delta = choice.get("delta") if isinstance(choice, dict) else {}
                    if isinstance(delta, dict) and delta.get("reasoning_content"):
                        reasoning_chars += len(str(delta.get("reasoning_content") or ""))
                    content = ""
                    if isinstance(delta, dict):
                        content = str(delta.get("content") or "")
                    if not content and isinstance(choice.get("message"), dict):
                        content = str(choice["message"].get("content") or "")
                    if not content:
                        # A non-content chunk (role-only delta / keep-alive) proves the connection
                        # is alive but is not a token, so it does not reset the idle-token timer.
                        continue
                    chunks.append(content)
                    tokens_generated += max(1, len(content.split()))
                    if not saw_token:
                        saw_token = True
                        self._set_response_timeout(resp, idle_token_sec)
                    last_token_mono = now
                    self._emit_progress(tokens_generated)
            except socket.timeout:
                # A blocking-read timeout maps to the same phase the wall-clock guards would
                # report: before-first-token if nothing has been generated yet, otherwise idle.
                phase = "llm_stalled_after_progress" if saw_token else "llm_stalled_before_first_token"
                raise _StreamTimeout(phase, tokens_generated=tokens_generated)
        raw_text = "".join(chunks)
        _thinking, output_text = split_thinking(raw_text)
        if self.last_usage:
            self.last_usage = _thinking_split_usage(
                self.last_usage, content_text=raw_text, reasoning_chars=reasoning_chars)
            logger.info(
                "llm token usage: prompt=%s thinking=%s output=%s completion=%s total=%s (model=%s)",
                self.last_usage.get("prompt_tokens"), self.last_usage.get("thinking_tokens"),
                self.last_usage.get("output_tokens"), self.last_usage.get("completion_tokens"),
                self.last_usage.get("total_tokens"), payload.get("model"))
            self._emit_usage(self.last_usage)
            self._emit_progress(int(self.last_usage.get("output_tokens") or tokens_generated))
        # Return only the model OUTPUT (any <think> block is reasoning, not the answer/JSON).
        return output_text

    def _emit_progress(self, tokens_generated: int) -> None:
        if self.on_progress is None:
            return
        try:
            self.on_progress({
                "tokens_generated": int(tokens_generated),
                "last_token_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            return

    def _emit_usage(self, usage: dict) -> None:
        if self.on_usage is None:
            return
        try:
            self.on_usage(dict(usage))
        except Exception:
            return

    def _set_response_timeout(self, resp, timeout_sec: float) -> None:
        for attr_path in (
            ("fp", "raw", "_sock"),
            ("fp", "raw", "_fp", "fp", "raw", "_sock"),
            ("_fp", "fp", "raw", "_sock"),
        ):
            target = resp
            try:
                for attr in attr_path:
                    target = getattr(target, attr)
                if hasattr(target, "settimeout"):
                    target.settimeout(timeout_sec)
                    return
            except Exception:
                continue


_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


def split_thinking(text: str) -> tuple[str, str]:
    """Split model output into (thinking_text, output_text) by extracting ``<think>…</think>``
    blocks. Models that don't emit thinking yield ("", text)."""
    if not text or "<think>" not in text.lower():
        return "", text
    thinking = "".join(m.group(1) for m in _THINK_BLOCK.finditer(text))
    output = _THINK_BLOCK.sub("", text)
    return thinking, output


def _thinking_split_usage(usage: dict, *, content_text: str, reasoning_chars: int) -> dict:
    """Enrich a usage dict with thinking_tokens / output_tokens / has_thinking using whichever
    signal the server provided: usage.completion_tokens_details.reasoning_tokens, separate
    reasoning_content deltas, or inline <think> blocks. Falls back to all-output."""
    completion = int(usage.get("completion_tokens") or 0)
    details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    reasoning_tokens = int(details.get("reasoning_tokens") or 0)
    thinking_text, _output = split_thinking(content_text or "")
    tag_chars = len(thinking_text)
    if reasoning_tokens > 0:
        thinking = min(reasoning_tokens, completion) if completion else reasoning_tokens
    elif completion and (reasoning_chars + len(content_text or "")) > 0:
        total_chars = reasoning_chars + len(content_text or "")
        thinking = round(completion * ((reasoning_chars + tag_chars) / total_chars)) if total_chars else 0
    else:
        thinking = 0
    out = dict(usage)
    out["thinking_tokens"] = int(thinking)
    out["output_tokens"] = max(0, completion - int(thinking))
    out["has_thinking"] = bool(reasoning_tokens or tag_chars or reasoning_chars)
    return out


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.environ.get(name, str(default)) or default))
    except Exception:
        return default


def _resolve_timeout(primary_env: str, fallback_env: str, default: float) -> float:
    """Resolve a timeout budget, preferring ``primary_env`` then ``fallback_env``.

    Empty/unset/invalid values fall through to the next source so a blank override never
    collapses the budget to a tiny number; the final default is clamped to >= 1s.
    """
    for name in (primary_env, fallback_env):
        if not name:
            continue
        raw = os.environ.get(name)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            return max(1.0, float(raw))
        except Exception:
            continue
    return max(1.0, float(default))
