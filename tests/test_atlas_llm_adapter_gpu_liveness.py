"""GPU-aware streaming liveness: a no-token gap is only a stall when the GPU has also fallen back to
its pre-generation baseline. While the GPU is still computing (long prefill / "think") the adapter
waits and heartbeats instead of timing out — server-side, independent of any browser. With no GPU
probe it degrades to the original time-only timeout.
"""
from __future__ import annotations

import socket
import time

import pytest

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter, AtlasLLMJsonRequest, _StreamTimeout

CONTENT = 'data: {"choices":[{"delta":{"content":"{\\"ok\\": true}"}}]}'
DONE = "data: [DONE]"


class _FakeResp:
    """Iterable SSE response: "TIMEOUT" entries sleep then raise socket.timeout (a no-byte poll),
    other entries are yielded as SSE lines."""

    def __init__(self, script):
        self._script = list(script)
        self._i = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._i >= len(self._script):
            raise StopIteration
        item = self._script[self._i]
        self._i += 1
        if item == "TIMEOUT":
            # Longer than the (>=1s clamped) no-token budget so a couple of these cross it.
            time.sleep(0.6)
            raise socket.timeout()
        return item.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _setup(monkeypatch, script):
    # Budgets clamp to a 1s floor, so each no-token gap (0.6s) crosses it within ~2 polls.
    monkeypatch.setenv("ATLAS_LLM_FIRST_TOKEN_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("ATLAS_LLM_IDLE_TOKEN_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("ATLAS_LLM_GPU_BUSY_MARGIN", "10")
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: _FakeResp(script))


def _req():
    return AtlasLLMJsonRequest(system_prompt="s", user_prompt="u")


def test_gpu_busy_waits_through_long_prefill(monkeypatch):
    # Several no-token poll-timeouts (a long prefill / think), then content. GPU goes from a low
    # baseline to busy -> the adapter must NOT time out; it waits and returns the content.
    _setup(monkeypatch, ["TIMEOUT", "TIMEOUT", "TIMEOUT", CONTENT, DONE])
    gpu = iter([5.0, 90.0, 90.0, 90.0, 90.0, 90.0])
    events: list[dict] = []
    ad = AtlasLLMJsonAdapter(
        base_url="http://x", model="m",
        on_progress=lambda p: events.append(p),
        gpu_sampler=lambda: next(gpu, 90.0))
    out = ad._post_chat_stream(_req(), structured=False)
    assert '"ok"' in out
    # A heartbeat was emitted during the busy no-token phase (liveness, browser-independent).
    assert any(e.get("reasoning_active") for e in events)


def test_gpu_idle_times_out(monkeypatch):
    # No tokens and GPU stays at ~baseline (model genuinely stopped) -> the stall fires.
    _setup(monkeypatch, ["TIMEOUT", "TIMEOUT", "TIMEOUT", "TIMEOUT", "TIMEOUT"])
    gpu = iter([5.0, 6.0, 6.0, 6.0, 6.0, 6.0, 6.0])
    ad = AtlasLLMJsonAdapter(base_url="http://x", model="m", gpu_sampler=lambda: next(gpu, 6.0))
    with pytest.raises(_StreamTimeout):
        ad._post_chat_stream(_req(), structured=False)


def test_no_gpu_probe_falls_back_to_time_only_timeout(monkeypatch):
    # No GPU probe available -> behaves like the original time-only timeout (stalls on a long gap).
    _setup(monkeypatch, ["TIMEOUT", "TIMEOUT", "TIMEOUT", "TIMEOUT"])
    ad = AtlasLLMJsonAdapter(base_url="http://x", model="m", gpu_sampler=lambda: None)
    with pytest.raises(_StreamTimeout):
        ad._post_chat_stream(_req(), structured=False)
