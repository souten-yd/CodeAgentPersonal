import json
from pathlib import Path

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest


def test_parse_plain_json() -> None:
    adapter = AtlasLLMJsonAdapter()
    assert adapter.parse_json_response('{"a":1}') == {"a": 1}


def test_parse_fenced_json_block() -> None:
    adapter = AtlasLLMJsonAdapter()
    text = '```json\n{"a":1}\n```'
    assert adapter.parse_json_response(text) == {"a": 1}


def test_parse_embedded_json_object() -> None:
    adapter = AtlasLLMJsonAdapter()
    assert adapter.parse_json_response('text {"a":1} text') == {"a": 1}


def test_parse_invalid_returns_none() -> None:
    adapter = AtlasLLMJsonAdapter()
    assert adapter.parse_json_response('not-json') is None


def test_generate_json_with_backend_fn_dict() -> None:
    adapter = AtlasLLMJsonAdapter(backend_fn=lambda _s, _u: {"ok": True})
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u"))
    assert result.ok is True
    assert result.data == {"ok": True}


def test_generate_json_with_backend_fn_string() -> None:
    adapter = AtlasLLMJsonAdapter(backend_fn=lambda _s, _u: '{"ok":true}')
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u"))
    assert result.ok is True
    assert result.data == {"ok": True}


def test_generate_json_backend_exception_returns_error() -> None:
    def _boom(_s: str, _u: str):
        raise RuntimeError("boom")

    adapter = AtlasLLMJsonAdapter(backend_fn=_boom)
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u"))
    assert result.ok is False
    assert result.error.startswith("llm_backend_error:")


def test_call_returns_dict_or_none() -> None:
    adapter_ok = AtlasLLMJsonAdapter(backend_fn=lambda _s, _u: '{"x":1}')
    adapter_ng = AtlasLLMJsonAdapter(backend_fn=lambda _s, _u: 'bad')
    assert adapter_ok("s", "u") == {"x": 1}
    assert adapter_ng("s", "u") is None


def test_generate_json_without_backend_returns_unavailable() -> None:
    adapter = AtlasLLMJsonAdapter()
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u"))
    assert result.ok is False
    assert result.error == "llm_backend_unavailable"


def test_openai_compatible_payload_shape_without_real_network(monkeypatch) -> None:
    captured = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"a":1}'}}]}).encode("utf-8")

    def _fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m")
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u"))
    assert captured["url"].endswith("/v1/chat/completions")
    assert "messages" in captured["data"]
    assert captured["data"]["response_format"]["type"] == "json_object"
    assert captured["data"]["model"] == "m"
    assert result.ok is True
    assert result.data == {"a": 1}


def test_adapter_has_no_forbidden_side_effect_tokens() -> None:
    source = Path("agent/atlas_llm_json_adapter.py").read_text(encoding="utf-8")
    for forbidden in [
        "subprocess",
        "safe_apply(",
        "run_command(",
        "TestCommandRunner(",
        "DebugLoopRunner(",
        "DeepResearch",
        "deep_research_job",
    ]:
        assert forbidden not in source
