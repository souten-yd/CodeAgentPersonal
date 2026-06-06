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


def test_streaming_socket_timeout_returns_llm_stalled(monkeypatch) -> None:
    def fake_urlopen(_req, timeout=0):
        return _StreamResp([_sse('{"a":')], timeout_after=0)

    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=lambda _p: None)

    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is False
    assert result.error == "llm_stalled"


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

