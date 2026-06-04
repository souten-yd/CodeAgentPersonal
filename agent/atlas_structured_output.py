"""Common structured-output generation: schema-constrained decoding + backend Pydantic validation.

This is the consolidation the proposal (PR-4) asks for. The flow is:

1. Call the LLM through :func:`call_llm_json`, threading a JSON schema so a capable llama-server / vLLM
   constrains decoding (grammar / json_schema). This is a *syntactic* guarantee only.
2. Validate the parsed object with an authoritative Pydantic model on the backend.
3. On a parse miss or a validation failure, retry up to ``max_attempts`` total, appending a strict
   reinforcement so the model is told to fix the structure.

The grammar is kept to syntax; meaning / safety / backend-authoritative decisions stay in the existing
server-side code. Callers keep their graceful fallbacks: on exhaustion we still return the best-effort
raw dict (and ``ok=False``), so behavior never regresses to worse than the pre-existing prompt-only path.

Backward compatible: a plain 2-arg ``Callable[[str, str], dict | None]`` (used widely in tests) is
invoked as-is by :func:`call_llm_json`; only the real adapter receives the schema.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Type

from pydantic import BaseModel, ValidationError

from agent.atlas_llm_json_adapter import call_llm_json

logger = logging.getLogger(__name__)

# Appended on a retry after a parse/validation miss. Mirrors the adapter's parse-retry reinforcement but
# is driven by *validation* failure (wrong shape/type), which the adapter alone cannot detect.
_REINFORCEMENT = (
    "\n\nIMPORTANT: The previous response did not match the required structure. Respond with a SINGLE "
    "valid JSON object that conforms EXACTLY to the JSON schema's fields and types. No prose, no "
    "markdown, no code fences."
)


@dataclass
class StructuredResult:
    """Outcome of a :func:`generate_structured` call.

    ``data`` is the best-effort raw dict (validated payload on success, last parsed payload on a
    validation failure, or ``None`` if nothing parsed) so callers can keep their existing default-filling.
    """

    ok: bool = False
    model: BaseModel | None = None
    data: dict | None = None
    attempts: int = 0
    warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)


def _summarize_validation_error(exc: ValidationError) -> list[str]:
    summaries: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        summaries.append(f"{loc or '<root>'}: {err.get('msg', 'invalid')}")
    return summaries[:8]


def generate_structured(
    llm_json_fn: Callable[[str, str], dict | None] | None,
    system_prompt: str,
    user_prompt: str,
    *,
    json_schema: dict | None,
    model: Type[BaseModel],
    max_attempts: int = 2,
) -> StructuredResult:
    """Generate a structured LLM output, validate it with ``model``, and retry on failure.

    Returns a :class:`StructuredResult`. ``max_attempts`` is the *total* number of LLM calls (default 2 =
    one retry); the standard for the proposal's "minimal retry".
    """
    result = StructuredResult()
    last_dict: dict | None = None
    attempt_prompt = user_prompt
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        result.attempts = attempt
        # Never let a flaky LLM transport crash the caller. The real adapter already swallows its own
        # errors, but a plain callable (or a retry's extra call) could raise; a structured-output helper
        # must degrade to "no usable JSON" exactly like a parse miss, so planning keeps its fallback
        # instead of bubbling an exception up to the planner bridge (which would discard the whole plan).
        try:
            raw = call_llm_json(llm_json_fn, system_prompt, attempt_prompt, json_schema=json_schema)
        except Exception as exc:  # noqa: BLE001
            logger.warning("structured_output_llm_call_failed model=%s attempt=%s error=%s", model.__name__, attempt, exc)
            result.warnings.append(f"structured_output_llm_call_failed:attempt_{attempt}")
            attempt_prompt = user_prompt + _REINFORCEMENT
            continue
        if not isinstance(raw, dict):
            result.warnings.append(f"structured_output_parse_failed:attempt_{attempt}")
            attempt_prompt = user_prompt + _REINFORCEMENT
            continue
        last_dict = raw
        try:
            instance = model.model_validate(raw)
        except ValidationError as exc:
            errors = _summarize_validation_error(exc)
            result.validation_errors = errors
            result.warnings.append(f"structured_output_validation_failed:attempt_{attempt}")
            logger.warning(
                "structured_output_validation_failed model=%s attempt=%s errors=%s",
                model.__name__,
                attempt,
                errors,
            )
            attempt_prompt = user_prompt + _REINFORCEMENT + "\nValidation errors to fix: " + "; ".join(errors)
            continue
        result.ok = True
        result.model = instance
        result.data = raw
        return result
    result.data = last_dict
    return result
