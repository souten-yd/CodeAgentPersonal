from types import SimpleNamespace
import threading

from app.lumen.tools import LumenToolResult
from app.services import lumen_runtime


def _deps(calls, events, statuses, saved):
    def execute(message, **kwargs):
        calls.append({"message": message, **kwargs})
        return {"status": "done", "output": "ok", "usage": {}, "steps": []}

    return SimpleNamespace(
        job_append_step=lambda project, job_id, seq, event_type, data: events.append((seq, event_type, data)),
        job_update_status=lambda project, job_id, status: statuses.append(status),
        job_log_append=lambda job_id, entry: None,
        execute_chat_with_optional_web_search=execute,
        save_session=lambda *args: saved.append(args),
        resolve_runtime_llm_url=lambda url: url or "http://llm",
        wait_threading=threading,
        job_wait_events={},
    )


def _req(message="横浜の天気"):
    return SimpleNamespace(
        project="default",
        message=message,
        mode="chat",
        max_steps=3,
        search_enabled=None,
        search_policy="auto",
        tool_policy="auto",
        search_budget={},
        weather_budget={"forecast_days": 3},
        news_budget={},
        location=None,
        llm_url="",
        chat_history=[],
    )


def test_tool_result_events_are_preceded_by_matching_tool_call(monkeypatch):
    monkeypatch.setattr(
        lumen_runtime,
        "execute_lumen_tool_plan",
        lambda **kwargs: [
            LumenToolResult(tool="weather", ok=True, content="weather context"),
            LumenToolResult(tool="news", ok=True, content="news context"),
        ],
    )
    calls, events, statuses, saved = [], [], [], []
    lumen_runtime.run_lumen_job_background_service("job-pair", _req(), _deps(calls, events, statuses, saved))

    event_types = [event_type for _, event_type, _ in events]
    weather_call_index = event_types.index("tool_call")
    weather_result_index = event_types.index("tool_result")
    assert weather_call_index < weather_result_index

    tool_events = [(event_type, data) for _, event_type, data in events if event_type in {"tool_call", "tool_result"}]
    assert tool_events[0][1]["id"] == tool_events[1][1]["id"] == "lumen-weather-0"
    assert tool_events[2][1]["id"] == tool_events[3][1]["id"] == "lumen-news-1"
    for index, (event_type, data) in enumerate(tool_events):
        assert event_type == ("tool_call" if index % 2 == 0 else "tool_result")
        assert data["source"] == "lumen"


def test_runtime_does_not_emit_standalone_tool_result(monkeypatch):
    monkeypatch.setattr(
        lumen_runtime,
        "execute_lumen_tool_plan",
        lambda **kwargs: [LumenToolResult(tool="weather", ok=True, content="weather context")],
    )
    calls, events, statuses, saved = [], [], [], []
    lumen_runtime.run_lumen_job_background_service("job-no-standalone", _req(), _deps(calls, events, statuses, saved))

    compact = [(event_type, data.get("id")) for _, event_type, data in events if event_type in {"tool_call", "tool_result"}]
    assert compact == [("tool_call", "lumen-weather-0"), ("tool_result", "lumen-weather-0")]
