"""Per-model structured-output profiles for local LLM serving (llama-server / vLLM, OpenAI-compatible).

Different local models react very differently to structured-output constraints, so a single
``response_format=json_schema`` policy is unsafe. This module maps a model name to the *preferred*
structured-output mode; the adapter still degrades gracefully at runtime if the server rejects a mode.

Modes
-----
- ``"json_schema"``: send ``response_format={"type":"json_schema", ...}`` (strict schema-constrained
  decoding). Strongest field-level guarantee. Good for models whose llama.cpp/vLLM schema→grammar path
  is reliable.
- ``"json_object"``: send ``response_format={"type":"json_object"}`` only (valid-JSON syntax, no field
  enforcement) and rely on the in-prompt schema hint + parser backstop. Safer for models that collapse
  under deep schema grammars.
- ``"grammar"``: send an explicit GBNF ``grammar`` when the request provides one, else json_object.
- ``"off"``: no structured constraint (prompt-only).

Priority models: Gemma 4 and Qwen 3.6. Also supported: Nemotron, gpt-oss.

Why the defaults
----------------
- **Gemma 4** has a known token-repetition / sampler-init collapse when a strict JSON schema is
  converted to GBNF (observed in llama.cpp and vLLM). We therefore default Gemma to ``json_object``,
  which uses a simple generic-JSON grammar (stable) plus our prompt schema hint. This still guarantees
  *syntactically valid* JSON — the main win — without triggering the collapse.
- **Qwen 3.x / 3.6** handles json_schema constrained decoding well → ``json_schema``.
- **Nemotron** and **gpt-oss** generally support json_schema on recent llama.cpp/vLLM → ``json_schema``.

Override
--------
``ATLAS_STRUCTURED_OUTPUT_MODE`` env var forces a single mode globally (handy for A/B on a given box).
"""
from __future__ import annotations

import os

VALID_MODES = {"json_schema", "json_object", "grammar", "off"}
DEFAULT_MODE = "json_schema"

# Ordered substring rules (first match wins). Keys are matched case-insensitively against the model id.
_MODEL_MODE_RULES: list[tuple[tuple[str, ...], str]] = [
    # Priority: Gemma 4 — avoid strict json_schema grammar collapse; valid-JSON via json_object.
    (("gemma",), "json_object"),
    # Priority: Qwen 3.x / 3.6 — reliable schema-constrained decoding.
    (("qwen",), "json_schema"),
    # Also supported.
    (("nemotron",), "json_schema"),
    (("gpt-oss", "gptoss", "gpt_oss"), "json_schema"),
]


def resolve_structured_mode(model_name: str | None) -> str:
    """Resolve the preferred structured-output mode for a model.

    Global env override wins; otherwise match known model families; otherwise DEFAULT_MODE.
    """
    forced = str(os.environ.get("ATLAS_STRUCTURED_OUTPUT_MODE", "")).strip().lower()
    if forced in VALID_MODES:
        return forced
    name = str(model_name or "").strip().lower()
    if not name:
        return DEFAULT_MODE
    for needles, mode in _MODEL_MODE_RULES:
        if any(n in name for n in needles):
            return mode
    return DEFAULT_MODE
