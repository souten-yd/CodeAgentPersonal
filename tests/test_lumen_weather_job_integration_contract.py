from types import SimpleNamespace
import threading

import pytest
from fastapi import HTTPException

from app.lumen.weather import LumenWeatherResult
from app.services.jobs import run_job_background_service, submit_job_service


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


def _req(message, **overrides):
    data = {
        "project": "default",
        "message": message,
        "mode": "chat",
        "max_steps": 3,
        "search_enabled": False,
        "search_policy": "auto",
        "tool_policy": "auto",
        "search_budget": {},
        "weather_budget": {"forecast_days": 3},
        "news_budget": {},
        "location": None,
        "llm_url": "",
        "chat_history": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_plain_chat_does_not_call_weather_tool(monkeypatch):
    weather_calls = []

    def fake_weather(*args, **kwargs):
        weather_calls.append((args, kwargs))
        raise AssertionError("weather should not run for pure chat")

    monkeypatch.setattr("app.lumen.tools.run_lumen_weather_tool", fake_weather)
    calls, events, statuses, saved = [], [], [], []
    run_job_background_service("job-chat", _req("こんちは"), _deps(calls, events, statuses, saved))

    assert weather_calls == []
    assert [event_type for _, event_type, _ in events if event_type == "tool_result"] == []
    assert calls[0]["internal_context"] == ""
    assert statuses[-1] == "done"


def test_tokyo_weather_creates_plan_tool_result_and_passes_context(monkeypatch):
    weather_calls = []

    def fake_weather(request):
        weather_calls.append(request)
        return LumenWeatherResult(
            ok=True,
            location_name="Tokyo",
            country="Japan",
            current_temperature=18.5,
            weather_code=3,
            weather_text="曇り",
            daily=[{"date": "2026-05-10", "temperature_max": 22, "temperature_min": 14, "precipitation_probability": 30, "weather_text": "曇り"}],
            forecast_dates=["2026-05-10"],
            fetched_at="2026-05-10T00:00:00+00:00",
        )

    monkeypatch.setattr("app.lumen.tools.run_lumen_weather_tool", fake_weather)
    calls, events, statuses, saved = [], [], [], []
    run_job_background_service("job-weather", _req("東京の天気"), _deps(calls, events, statuses, saved))

    tool_plan_events = [data for _, event_type, data in events if event_type == "tool_plan"]
    tool_result_events = [data for _, event_type, data in events if event_type == "tool_result"]
    assert tool_plan_events[0]["tools"] == ["weather"]
    assert tool_plan_events[0]["metadata"]["executable"] is True
    assert len(weather_calls) == 1
    assert weather_calls[0].location == "東京"
    assert len(tool_result_events) == 1
    assert tool_result_events[0]["tool"] == "weather"
    assert tool_result_events[0]["ok"] is True
    assert "[Internal Lumen Weather Context]" in calls[0]["internal_context"]
    assert "Tokyo" in calls[0]["internal_context"]
    assert "Do not invent weather data" in calls[0]["internal_context"]


def test_tool_policy_off_does_not_call_weather_tool(monkeypatch):
    weather_calls = []

    def fake_weather(request):
        weather_calls.append(request)
        return LumenWeatherResult(ok=True)

    monkeypatch.setattr("app.lumen.tools.run_lumen_weather_tool", fake_weather)
    calls, events, statuses, saved = [], [], [], []
    run_job_background_service("job-off", _req("東京の天気", tool_policy="off"), _deps(calls, events, statuses, saved))

    assert weather_calls == []
    assert [data for _, event_type, data in events if event_type == "tool_result"] == []
    assert calls[0]["internal_context"] == ""


def test_weather_failure_context_forbids_fabrication(monkeypatch):
    def fake_weather(request):
        return LumenWeatherResult(ok=False, error="forecast_failed", message="天気予報の取得に失敗しました")

    monkeypatch.setattr("app.lumen.tools.run_lumen_weather_tool", fake_weather)
    calls, events, statuses, saved = [], [], [], []
    run_job_background_service("job-fail", _req("東京の天気"), _deps(calls, events, statuses, saved))

    tool_result_events = [data for _, event_type, data in events if event_type == "tool_result"]
    assert tool_result_events[0]["ok"] is False
    assert tool_result_events[0]["metadata"]["error"] == "forecast_failed"
    assert "could not be obtained" in calls[0]["internal_context"]
    assert "Do not invent weather data" in calls[0]["internal_context"]


def test_location_required_context_is_passed_without_guessing(monkeypatch):
    # Use the real weather tool path to verify no location guessing occurs.
    calls, events, statuses, saved = [], [], [], []
    run_job_background_service("job-location", _req("今日の天気を教えて"), _deps(calls, events, statuses, saved))

    tool_result_events = [data for _, event_type, data in events if event_type == "tool_result"]
    assert tool_result_events[0]["ok"] is False
    assert tool_result_events[0]["metadata"]["error"] == "location_required"
    assert "地域を指定" in calls[0]["internal_context"]


def test_task_mode_still_rejected_before_job_creation():
    req = SimpleNamespace(project="default", message="東京の天気", mode="task")
    with pytest.raises(HTTPException) as excinfo:
        submit_job_service(
            req,
            create_job=lambda *args: "job-should-not-exist",
            thread_factory=lambda **kwargs: None,
            background_runner=lambda *args: None,
            current_model_key="contract-model",
        )

    assert excinfo.value.status_code == 410
    assert excinfo.value.detail["error"] == "legacy_task_mode_removed"
