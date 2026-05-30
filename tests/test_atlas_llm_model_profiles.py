import json

import agent.atlas_llm_json_adapter as adapter_mod
from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest
from agent.atlas_llm_model_profiles import DEFAULT_MODE, resolve_structured_mode
from agent.atlas_llm_schemas import patch_proposal_json_schema


def test_priority_models_resolve_to_expected_modes():
    # Priority: Gemma 4 avoids strict json_schema collapse -> json_object.
    assert resolve_structured_mode("gemma-4-E4B-it-Q4_K_M") == "json_object"
    # Priority: Qwen 3.6 handles schema-constrained decoding -> json_schema.
    assert resolve_structured_mode("Qwen3.6-7B-Instruct") == "json_schema"


def test_secondary_models_and_default():
    assert resolve_structured_mode("nvidia-nemotron-4") == "json_schema"
    assert resolve_structured_mode("gpt-oss-20b") == "json_schema"
    assert resolve_structured_mode("gpt_oss-120b") == "json_schema"
    assert resolve_structured_mode("llama-3.1-8b") == DEFAULT_MODE
    assert resolve_structured_mode("") == DEFAULT_MODE
    assert resolve_structured_mode(None) == DEFAULT_MODE


def test_env_override_forces_mode(monkeypatch):
    monkeypatch.setenv("ATLAS_STRUCTURED_OUTPUT_MODE", "off")
    assert resolve_structured_mode("Qwen3.6") == "off"
    monkeypatch.setenv("ATLAS_STRUCTURED_OUTPUT_MODE", "json_object")
    assert resolve_structured_mode("gpt-oss") == "json_object"
    # Invalid override is ignored -> falls back to model rules.
    monkeypatch.setenv("ATLAS_STRUCTURED_OUTPUT_MODE", "nonsense")
    assert resolve_structured_mode("Qwen3.6") == "json_schema"


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture_response_format(monkeypatch, model):
    schema = patch_proposal_json_schema(require_content=True)
    ad = AtlasLLMJsonAdapter(base_url="http://local", model=model)
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        ok = json.dumps({"choices": [{"message": {"content": '{"proposed_content":"x","risk_level":"low"}'}}]})
        return _FakeResp(ok.encode("utf-8"))

    monkeypatch.setattr(adapter_mod.urllib_request, "urlopen", fake_urlopen)
    ad.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", json_schema=schema, model=model))
    return captured["payload"]


def test_gemma_payload_uses_json_object_not_strict_schema(monkeypatch):
    payload = _capture_response_format(monkeypatch, "gemma-4-E4B-it")
    assert payload["response_format"]["type"] == "json_object"
    # The schema is still conveyed to the model via the prompt hint.
    assert "proposed_content" in payload["messages"][-1]["content"]


def test_qwen_payload_uses_strict_json_schema(monkeypatch):
    payload = _capture_response_format(monkeypatch, "Qwen3.6-7B")
    rf = payload["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
