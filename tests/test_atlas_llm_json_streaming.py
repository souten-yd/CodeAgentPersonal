import json
import socket
from types import SimpleNamespace

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest


class _Sock:
    def __init__(self) -> None:
        self.timeouts = []

    def settimeout(self, value) -> None:
        self.timeouts.append(value)


class _StreamResp:
    def __init__(self, lines, *, sock: _Sock | None = None, timeout_after: int | None = None) -> None:
        self.lines = list(lines)
        self.sock = sock or _Sock()
        self.timeout_after = timeout_after
        self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=self.sock))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        for index, line in enumerate(self.lines):
            if self.timeout_after is not None and index >= self.timeout_after:
                raise socket.timeout("stalled")
            yield line


class _ReadResp:
    def __init__(self, content: str) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode("utf-8")


def _sse(content: str) -> bytes:
    return ("data: " + json.dumps({"choices": [{"delta": {"content": content}}]}) + "\n\n").encode("utf-8")


def test_streaming_concatenates_sse_chunks_and_reports_progress(monkeypatch) -> None:
    captured = {}
    progress = []

    def fake_urlopen(req, timeout=0):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _StreamResp([_sse('{"a":'), _sse("1}"), b"data: [DONE]\n\n"])

    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=progress.append)

    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is True
    assert result.data == {"a": 1}
    assert captured["payload"]["stream"] is True
    assert captured["timeout"] == 300.0
    assert [p["tokens_generated"] for p in progress] == [1, 2]
    assert all(p["last_token_at"] for p in progress)


def test_streaming_socket_timeout_before_first_token_reason(monkeypatch) -> None:
    def fake_urlopen(_req, timeout=0):
        return _StreamResp([_sse('{"a":')], timeout_after=0)

    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=lambda _p: None)

    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is False
    # A read timeout before any content token is a truthful before-first-token stall, not a
    # flat "llm_stalled", so the planner can distinguish prefill failure from idle generation.
    assert result.error == "llm_stalled_before_first_token"
    assert result.metadata.get("timeout_phase") == "llm_stalled_before_first_token"


def test_streaming_uses_first_token_then_stall_timeouts(monkeypatch) -> None:
    sock = _Sock()
    captured = {}

    def fake_urlopen(_req, timeout=0):
        captured["timeout"] = timeout
        return _StreamResp([_sse('{"a":1}'), b"data: [DONE]\n\n"], sock=sock)

    monkeypatch.setenv("ATLAS_PLAN_FIRST_TOKEN_SEC", "7")
    monkeypatch.setenv("ATLAS_LLM_INTER_TOKEN_SEC", "5")
    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=lambda _p: None)

    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is True
    assert captured["timeout"] == 7.0
    # after first token, socket timeout switches to ATLAS_LLM_INTER_TOKEN_SEC (not stall_after_sec)
    assert sock.timeouts == [7.0, 5.0]


def test_streaming_env_zero_uses_blocking_path(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _ReadResp('{"a":1}')

    monkeypatch.setenv("ATLAS_LLM_STREAMING", "0")
    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=lambda _p: None)

    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is True
    assert result.data == {"a": 1}
    assert "stream" not in captured["payload"]



def _sse_usage(prompt: int, completion: int) -> bytes:
    return ("data: " + json.dumps({
        "choices": [], "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                                  "total_tokens": prompt + completion}}) + "\n\n").encode("utf-8")


def test_streaming_captures_real_token_usage(monkeypatch) -> None:
    captured = {}
    progress = []

    def fake_urlopen(req, timeout=0):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        # content chunks, then a final usage chunk (stream_options.include_usage), then DONE
        return _StreamResp([_sse('{"a":'), _sse("1}"), _sse_usage(1784, 101), b"data: [DONE]\n\n"])

    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=progress.append)
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is True and result.data == {"a": 1}
    # Real prompt/completion/total counts + a thinking/output split (this plain model has no
    # thinking -> all output).
    assert captured["payload"]["stream_options"] == {"include_usage": True}
    assert adapter.last_usage["prompt_tokens"] == 1784
    assert adapter.last_usage["completion_tokens"] == 101
    assert adapter.last_usage["thinking_tokens"] == 0
    assert adapter.last_usage["output_tokens"] == 101
    assert adapter.last_usage["has_thinking"] is False
    assert progress[-1]["tokens_generated"] == 101


def test_non_streaming_captures_usage(monkeypatch) -> None:
    class _ReadRespUsage(_ReadResp):
        def read(self):
            return json.dumps({"choices": [{"message": {"content": '{"a":1}'}}],
                               "usage": {"prompt_tokens": 50, "completion_tokens": 7, "total_tokens": 57}}).encode("utf-8")

    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen",
                        lambda req, timeout=0: _ReadRespUsage('{"a":1}'))
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m")
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=False))
    assert result.ok is True
    assert adapter.last_usage["total_tokens"] == 57


def _sse_reasoning(text: str) -> bytes:
    return ("data: " + json.dumps({"choices": [{"delta": {"reasoning_content": text}}]}) + "\n\n").encode("utf-8")


def test_thinking_split_from_reasoning_content(monkeypatch) -> None:
    usages = []

    def fake_urlopen(req, timeout=0):
        # reasoning_content deltas (thinking) then content, then usage with completion_tokens=100
        return _StreamResp([_sse_reasoning("let me think hard about this"),
                            _sse('{"a":'), _sse("1}"), _sse_usage(20, 100), b"data: [DONE]\n\n"])

    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_usage=usages.append)
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is True and result.data == {"a": 1}  # returned content is OUTPUT only
    u = adapter.last_usage
    assert u["has_thinking"] is True
    assert u["thinking_tokens"] > 0 and u["output_tokens"] < 100
    assert u["thinking_tokens"] + u["output_tokens"] == 100
    assert usages and usages[-1]["has_thinking"] is True  # on_usage fired


def test_think_tag_block_is_stripped_from_output(monkeypatch) -> None:
    def fake_urlopen(req, timeout=0):
        return _StreamResp([_sse("<think>reasoning here</think>"), _sse('{"a":1}'),
                            _sse_usage(10, 40), b"data: [DONE]\n\n"])

    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m")
    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))
    # The <think> block is reasoning, not the answer -> stripped; JSON still parses.
    assert result.ok is True and result.data == {"a": 1}
    assert adapter.last_usage["has_thinking"] is True
    assert adapter.last_usage["thinking_tokens"] > 0
