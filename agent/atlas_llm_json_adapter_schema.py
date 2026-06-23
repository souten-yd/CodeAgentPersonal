from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasLLMJsonRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    schema_hint: str = ""
    json_schema: dict | None = None
    grammar: str = ""
    model: str = ""
    temperature: float = 0.1
    # Output token cap. 16384 (was 8192/4096): a whole large file's edits can exceed 8192 output
    # tokens — hitting 8192 truncates the JSON mid-response, which is invalid and triggers endless
    # regeneration. The adapter's per-call budget (`_budgeted_max_tokens`) still caps this to what
    # actually FITS the context window (n_ctx - prompt - margin), so a larger default never overflows;
    # it only lets a big context (e.g. 32768) produce a complete large file. Override per-call where a
    # deliberately small response is wanted.
    max_tokens: int = 16384
    timeout_seconds: int = 120
    stream: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasLLMJsonResult(BaseModel):
    ok: bool = False
    data: dict = Field(default_factory=dict)
    raw_text: str = ""
    model: str = ""
    backend: str = ""
    structured: bool = False
    structured_fallback: bool = False
    used_fallback: bool = False
    error: str = ""
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
