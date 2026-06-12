"""PFG-34 — optional OpenRouter live smoke gate.

A live OpenRouter call runs ONLY when explicitly opted in: FORGE_OPENROUTER_LIVE_SMOKE=1
AND an API key in OPENROUTER_API_KEY. Otherwise the test skips — it is never reported as
a passed live check (unavailable != passed). When it does run, it asserts a genuine
response and records exact evidence (model id, latency, usage) with NO secret.

CI without a key skips and stays green.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent.model_forge.providers.openrouter_client import OpenRouterProvider
from agent.model_forge.providers.openrouter_config import (
    OpenRouterConfig,
    live_smoke_enabled,
    redact_openrouter_headers,
)
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeExecutionRequest
from agent.model_forge.source_policy import PrivacyMode, SourceMode
from agent.model_forge.stage_taxonomy import ForgeStage

_SMOKE_MODEL = os.environ.get("FORGE_OPENROUTER_MODEL", "openai/gpt-4o-mini")


def _smoke_resolver(_request: ForgeExecutionRequest) -> tuple[str, str]:
    return "You are a test.", "Reply with the single word: ok"


@pytest.mark.real_model
def test_openrouter_live_smoke_is_gated_and_secret_free():
    config = OpenRouterConfig(enabled=True)
    if not live_smoke_enabled(config):
        # Truthful: live OpenRouter is unavailable here. This is NOT a passed live check.
        pytest.skip("OpenRouter live smoke not enabled (need FORGE_OPENROUTER_LIVE_SMOKE=1 + OPENROUTER_API_KEY)")

    provider = OpenRouterProvider(config=config, model_id=_SMOKE_MODEL, prompt_resolver=_smoke_resolver)
    request = ForgeExecutionRequest(
        request_id="pfg34_smoke", stage=ForgeStage.REVIEW, route_id=ForgeRoute.DIRECT_PATCH,
        source_mode=SourceMode.FRONTIER_PREFERRED, privacy_mode=PrivacyMode.REDACTED_ONLY,
    )
    result = provider.execute_chat_completion(request)

    assert result.contract_valid is True, result.errors
    assert result.latency_ms > 0
    assert result.errors == []

    # No secret may appear anywhere in the recorded result.
    blob = result.model_dump_json()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    assert key and key not in blob
    # Header redaction masks the Authorization value.
    redacted = redact_openrouter_headers({"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    assert key not in json.dumps(redacted)

    evidence = {
        "package": "PFG-34", "model_id": result.model_id, "latency_ms": result.latency_ms,
        "input_tokens": result.usage.input_tokens, "output_tokens": result.usage.output_tokens,
        "contract_valid": result.contract_valid, "secret_recorded": False,
    }
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pfg34_openrouter_live_smoke.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PFG-34 evidence:", json.dumps(evidence, ensure_ascii=False))
