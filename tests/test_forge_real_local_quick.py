"""PFG-30 — real local-model Quick preset run.

Runs a Quick-preset task through the real LocalOpenAICompatibleProvider against a live
local OpenAI-compatible server. This is REAL model evidence: it is skipped (not failed)
when no server is reachable, so CI without a model stays green, and when a server is
present it requires a genuine, contract-valid model response.

Point it at a server with FORGE_LOCAL_BASE_URL (default http://localhost:8080).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from agent.model_forge.providers.local_openai_compatible import LocalOpenAICompatibleProvider
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeExecutionRequest
from agent.model_forge.stage_taxonomy import ForgeStage

BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://localhost:8080").rstrip("/")

_QUICK_SYSTEM = "You are a precise coding assistant. Output only what is asked, no prose."
_QUICK_USER = (
    "Write a single Python function `add(a, b)` that returns a + b. "
    "Respond with ONLY the function definition."
)


def _server_model() -> str | None:
    try:
        with urllib.request.urlopen(BASE_URL + "/v1/models", timeout=3) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    models = data.get("data") or data.get("models") or []
    if not models:
        return ""
    first = models[0]
    return str(first.get("id") or first.get("name") or "")


def _quick_resolver(_request: ForgeExecutionRequest) -> tuple[str, str]:
    return _QUICK_SYSTEM, _QUICK_USER


@pytest.mark.real_model
def test_real_local_quick_preset_run():
    model = _server_model()
    if model is None:
        pytest.skip(f"no local model server reachable at {BASE_URL}")

    provider = LocalOpenAICompatibleProvider(
        base_url=BASE_URL, model_id=model or "", prompt_resolver=_quick_resolver, timeout_seconds=120.0,
    )
    request = ForgeExecutionRequest(
        request_id="pfg30_quick", stage=ForgeStage.PATCH_GENERATION,
        route_id=ForgeRoute.MICRO_PATCH, task_category="quick", output_contract="text",
    )
    result = provider.execute_chat_completion(request)

    # Real model evidence: a genuine, contract-valid response with measured latency/usage.
    assert result.contract_valid is True, result.errors
    assert result.errors == []
    assert result.latency_ms > 0
    assert result.usage.output_tokens > 0

    # Capture the actual model output once for the recorded evidence artifact.
    payload = {
        "messages": [
            {"role": "system", "content": _QUICK_SYSTEM},
            {"role": "user", "content": _QUICK_USER},
        ],
        "stream": False, "temperature": 0,
    }
    if model:
        payload["model"] = model
    req = urllib.request.Request(
        BASE_URL + "/v1/chat/completions", method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        body = json.loads(resp.read().decode("utf-8", "replace"))
    output_text = body["choices"][0]["message"]["content"]
    assert "def add" in output_text

    evidence = {
        "package": "PFG-30",
        "base_url": BASE_URL,
        "model_id": result.model_id,
        "latency_ms": result.latency_ms,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "contract_valid": result.contract_valid,
        "output_excerpt": output_text[:400],
    }
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "model_forge" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pfg30_quick_local.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PFG-30 evidence:", json.dumps(evidence, ensure_ascii=False))
