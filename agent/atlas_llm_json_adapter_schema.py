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
    # Output token cap. 8192 (was 4096): a whole file + test can exceed 4096 output tokens, and a
    # truncated response is invalid JSON that triggers endless regeneration. Override per-call /
    # per-model where needed.
    max_tokens: int = 8192
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
