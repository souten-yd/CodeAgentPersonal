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


def test_parse_repairs_truncated_object() -> None:
    adapter = AtlasLLMJsonAdapter()
    # Output cut off at max_tokens mid-array; the complete leading element is recovered and the
    # half-written trailing element is dropped.
    text = '{"findings": [{"severity": "high", "title": "A"}, {"sev'
    parsed = adapter.parse_json_response(text)
    assert parsed == {"findings": [{"severity": "high", "title": "A"}]}


def test_parse_salvages_valid_prefix_before_corrupt_tail() -> None:
    adapter = AtlasLLMJsonAdapter()
    # The exact failure shape from the log: a well-formed finding prefix, then the model degrades
    # into invalid tokens. The valid prefix (incl. the high-severity finding) is recovered.
    raw = (
        '{\n  "findings": [\n    {\n      "severity": "high",\n'
        '      "title": "Missing Accessibility Considerations",\n'
        '      "detail": "No ARIA",\n      "recommendation": "Add ARIA",\n'
        '      "angle_risk": "high",\n      "category: ":-1,"\n      ":"angle"\n    },\n'
    )
    parsed = adapter.parse_json_response(raw)
    assert isinstance(parsed, dict)
    findings = parsed.get("findings")
    assert isinstance(findings, list) and findings
    assert findings[0]["severity"] == "high"
    assert findings[0]["title"] == "Missing Accessibility Considerations"


def test_parse_repair_rejects_unsalvageable_garbage() -> None:
    adapter = AtlasLLMJsonAdapter()
    assert adapter.parse_json_response('{ totally :: broken "') is None


def test_generate_json_retries_once_on_parse_failure(monkeypatch) -> None:
    calls = {"n": 0, "prompts": []}

    class _Resp:
        def __init__(self, content: str):
            self._content = content

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": self._content}}]}).encode("utf-8")

    def _fake_urlopen(req, timeout=0):
        calls["n"] += 1
        calls["prompts"].append(json.loads(req.data.decode("utf-8"))["messages"][-1]["content"])
        # First response is broken JSON; the one-shot strict retry returns valid JSON.
        return _Resp('{"a": 1, ' if calls["n"] == 1 else '{"a": 1}')

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m")
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u"))
    assert calls["n"] == 2
    assert result.ok is True
    assert result.data == {"a": 1}
    assert "llm_json_parse_retry_succeeded" in result.warnings
    # The retry reinforces a strict JSON-only instruction.
    assert "valid JSON" in calls["prompts"][1]


def test_resolve_n_ctx_prefers_explicit_constructor_value_over_hardcoded_default(monkeypatch) -> None:
    # Reproduced live: a model served with a large context (e.g. 65535/131072, configured through
    # the app's OWN settings UI rather than an env var) still had its adapter fall back to the
    # hardcoded 16384 default, because _resolve_n_ctx only ever consulted env vars. A ~25K-token
    # patch-generation prompt (very reasonable for editing an existing ~500-line file) was then
    # rejected as "over budget" (avail < 0), flooring output to 512 tokens and producing an
    # empty/unusable completion after all retries.
    for key in ("ATLAS_LLM_N_CTX", "LLAMA_CTX_SIZE", "DEFAULT_LLM_CTX_SIZE"):
        monkeypatch.delenv(key, raising=False)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", n_ctx=65535)
    assert adapter._resolve_n_ctx() == 65535


def test_resolve_n_ctx_falls_back_to_env_then_hardcoded_default(monkeypatch) -> None:
    for key in ("ATLAS_LLM_N_CTX", "LLAMA_CTX_SIZE", "DEFAULT_LLM_CTX_SIZE"):
        monkeypatch.delenv(key, raising=False)
    # No explicit n_ctx and no env vars -> the pre-existing hardcoded default, unchanged.
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m")
    assert adapter._resolve_n_ctx() == 16384

    monkeypatch.setenv("LLAMA_CTX_SIZE", "32768")
    adapter_env = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m")
    assert adapter_env._resolve_n_ctx() == 32768


def test_budgeted_max_tokens_uses_the_real_served_context_not_the_hardcoded_default(monkeypatch) -> None:
    for key in ("ATLAS_LLM_N_CTX", "LLAMA_CTX_SIZE", "DEFAULT_LLM_CTX_SIZE"):
        monkeypatch.delenv(key, raising=False)
    # A ~15K-char (roughly ~4-5K token) prompt: comfortably fits a real 65535 context with room
    # for a full-file output, but would floor to the 512-token minimum under the old hardcoded
    # 16384 default once twin/requirement/context overhead pushed the estimated prompt over it.
    messages = [{"role": "user", "content": "x" * 60000}]

    starved = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", n_ctx=16384)
    assert starved._budgeted_max_tokens(messages, requested=0) == 512

    healthy = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", n_ctx=65535)
    assert healthy._budgeted_max_tokens(messages, requested=0) > 512


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
