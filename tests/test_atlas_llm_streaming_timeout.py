"""PIBIH-1: phase-aware streaming planning timeout hardening.

These tests drive ``AtlasLLMJsonAdapter._post_chat_stream`` through a fake streaming
backend plus a fake monotonic clock so the three timeout budgets — first-token, idle-token,
and total — can be exercised deterministically without real delays. The key property under
test is that a slow-but-progressing model resets the idle timer on every real content token
and is never reported as stalled merely for being slow, while genuine stalls surface a
truthful phase-specific terminal reason.
"""

import json
from types import SimpleNamespace

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest


class _FakeClock:
    """A controllable monotonic clock; the stream iterator advances it per line."""

    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t


class _Sock:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def settimeout(self, value) -> None:
        self.timeouts.append(value)


class _TimedStreamResp:
    """A streaming response whose iteration advances a shared fake clock.

    ``steps`` is a list of ``(advance_seconds, line_bytes_or_none)``. Before each line is
    yielded the clock is advanced by ``advance_seconds`` so the adapter's per-line wall-clock
    guards observe the intended elapsed time. ``None`` lines are skipped (used only to advance
    time, though heartbeat byte lines are preferred for realism).
    """

    def __init__(self, steps, clock: _FakeClock, *, sock: _Sock | None = None) -> None:
        self.steps = list(steps)
        self.clock = clock
        self.sock = sock or _Sock()
        self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=self.sock))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        for advance, line in self.steps:
            self.clock.t += float(advance)
            if line is None:
                continue
            yield line


def _content(text: str) -> bytes:
    return ("data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n").encode("utf-8")


def _heartbeat() -> bytes:
    # A non-content delta (role-only / keep-alive): proves the connection is alive but is not a token.
    return b'data: {"choices": [{"delta": {}}]}\n\n'


_DONE = b"data: [DONE]\n\n"


def _adapter(monkeypatch, clock: _FakeClock, **env) -> AtlasLLMJsonAdapter:
    monkeypatch.setattr("agent.atlas_llm_json_adapter.time.monotonic", clock.monotonic)
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    return AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=lambda _p: None)


def _run(adapter):
    return adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))


def test_long_first_token_wait_then_valid_json_succeeds(monkeypatch) -> None:
    clock = _FakeClock()
    steps = [(50, _heartbeat()), (40, _content('{"a":1}')), (1, _DONE)]
    adapter = _adapter(
        monkeypatch, clock,
        ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=100,
        ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS=100,
        ATLAS_LLM_TOTAL_TIMEOUT_SECONDS=1000,
    )
    monkeypatch.setattr(
        "agent.atlas_llm_json_adapter.urllib_request.urlopen",
        lambda _req, timeout=0: _TimedStreamResp(steps, clock),
    )

    result = _run(adapter)

    assert result.ok is True
    assert result.data == {"a": 1}


def test_continuous_slow_token_stream_succeeds(monkeypatch) -> None:
    clock = _FakeClock()
    # Each gap (40s) is below the idle budget (50s); a progressing model must not stall.
    steps = [(10, _content('{"a":')), (40, _content("1,")), (40, _content('"b":2}')), (1, _DONE)]
    adapter = _adapter(
        monkeypatch, clock,
        ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=100,
        ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS=50,
        ATLAS_LLM_TOTAL_TIMEOUT_SECONDS=1000,
    )
    monkeypatch.setattr(
        "agent.atlas_llm_json_adapter.urllib_request.urlopen",
        lambda _req, timeout=0: _TimedStreamResp(steps, clock),
    )

    result = _run(adapter)

    assert result.ok is True
    assert result.data == {"a": 1, "b": 2}


def test_no_first_token_fails_before_first_token(monkeypatch) -> None:
    clock = _FakeClock()
    # Heartbeats keep the socket alive past the first-token budget without producing a token.
    steps = [(20, _heartbeat()), (20, _heartbeat()), (20, _content('{"a":1}')), (1, _DONE)]
    adapter = _adapter(
        monkeypatch, clock,
        ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=30,
        ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS=100,
        ATLAS_LLM_TOTAL_TIMEOUT_SECONDS=1000,
    )
    monkeypatch.setattr(
        "agent.atlas_llm_json_adapter.urllib_request.urlopen",
        lambda _req, timeout=0: _TimedStreamResp(steps, clock),
    )

    result = _run(adapter)

    assert result.ok is False
    assert result.error == "llm_stalled_before_first_token"
    assert result.metadata.get("timeout_phase") == "llm_stalled_before_first_token"


def test_one_token_then_idle_fails_after_progress(monkeypatch) -> None:
    clock = _FakeClock()
    steps = [(10, _content('{"a":1}')), (20, _heartbeat()), (20, _heartbeat()), (1, _DONE)]
    adapter = _adapter(
        monkeypatch, clock,
        ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=100,
        ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS=30,
        ATLAS_LLM_TOTAL_TIMEOUT_SECONDS=1000,
    )
    monkeypatch.setattr(
        "agent.atlas_llm_json_adapter.urllib_request.urlopen",
        lambda _req, timeout=0: _TimedStreamResp(steps, clock),
    )

    result = _run(adapter)

    assert result.ok is False
    assert result.error == "llm_stalled_after_progress"
    assert result.metadata.get("timeout_phase") == "llm_stalled_after_progress"
    assert result.metadata.get("tokens_generated") == 1


def test_total_timeout_is_distinct_from_first_and_idle(monkeypatch) -> None:
    clock = _FakeClock()
    # Tokens keep flowing within the idle budget, but the absolute total budget (40s) is hit.
    steps = [(10, _content('{"a":')), (10, _content("1,")), (10, _content('"b":')), (20, _content("2}")), (1, _DONE)]
    adapter = _adapter(
        monkeypatch, clock,
        ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=1000,
        ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS=1000,
        ATLAS_LLM_TOTAL_TIMEOUT_SECONDS=40,
    )
    monkeypatch.setattr(
        "agent.atlas_llm_json_adapter.urllib_request.urlopen",
        lambda _req, timeout=0: _TimedStreamResp(steps, clock),
    )

    result = _run(adapter)

    assert result.ok is False
    assert result.error == "llm_total_timeout"
    assert result.metadata.get("timeout_phase") == "llm_total_timeout"


def test_malformed_first_output_then_valid_structured_retry(monkeypatch) -> None:
    clock = _FakeClock()
    calls = {"n": 0}

    def fake_urlopen(_req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            return _TimedStreamResp([(1, _content("not json at all")), (1, _DONE)], clock)
        return _TimedStreamResp([(1, _content('{"a":1}')), (1, _DONE)], clock)

    adapter = _adapter(
        monkeypatch, clock,
        ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=1000,
        ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS=1000,
        ATLAS_LLM_TOTAL_TIMEOUT_SECONDS=10000,
    )
    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)

    result = _run(adapter)

    assert result.ok is True
    assert result.data == {"a": 1}
    assert calls["n"] == 2
    assert "llm_json_parse_retry_succeeded" in result.warnings


def test_new_env_names_take_precedence_over_legacy(monkeypatch) -> None:
    clock = _FakeClock()
    captured = {}

    def fake_urlopen(_req, timeout=0):
        captured["timeout"] = timeout
        return _TimedStreamResp([(1, _content('{"a":1}')), (1, _DONE)], clock)

    # New name should win over the legacy ATLAS_PLAN_FIRST_TOKEN_SEC fallback.
    adapter = _adapter(
        monkeypatch, clock,
        ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS=222,
        ATLAS_PLAN_FIRST_TOKEN_SEC=7,
    )
    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)

    result = _run(adapter)

    assert result.ok is True
    assert captured["timeout"] == 222.0


def test_legacy_env_names_still_apply_when_new_absent(monkeypatch) -> None:
    clock = _FakeClock()
    sock = _Sock()
    captured = {}

    def fake_urlopen(_req, timeout=0):
        captured["timeout"] = timeout
        return _TimedStreamResp([(1, _content('{"a":1}')), (1, _DONE)], clock, sock=sock)

    monkeypatch.setattr("agent.atlas_llm_json_adapter.time.monotonic", clock.monotonic)
    monkeypatch.setenv("ATLAS_PLAN_FIRST_TOKEN_SEC", "7")
    monkeypatch.setenv("ATLAS_LLM_INTER_TOKEN_SEC", "5")
    monkeypatch.delenv("ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr("agent.atlas_llm_json_adapter.urllib_request.urlopen", fake_urlopen)
    adapter = AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="m", on_progress=lambda _p: None)

    result = adapter.generate_json(AtlasLLMJsonRequest(system_prompt="s", user_prompt="u", stream=True))

    assert result.ok is True
    assert captured["timeout"] == 7.0
    # First-token socket timeout, then idle-token timeout after the first real token.
    assert sock.timeouts == [7.0, 5.0]
