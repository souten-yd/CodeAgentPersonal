from fastapi.testclient import TestClient

from app.api.echo import (
    default_echo_save_status_payload,
    default_echo_sessions_payload,
)
from app.server import create_app
import main


def test_create_app_echo_read_only_endpoints_return_fallback_payloads():
    client = TestClient(create_app())

    save_status = client.get("/echo/save-status")
    sessions = client.get("/echo/sessions")
    session = client.get("/echo/sessions/missing-session.wav")

    assert save_status.status_code == 200
    assert save_status.json() == default_echo_save_status_payload()
    assert sessions.status_code == 200
    assert sessions.json() == default_echo_sessions_payload()
    assert session.status_code == 404
    assert session.json() == {"detail": "ファイルが見つかりません"}


def test_create_app_echo_fallbacks_do_not_touch_filesystem_or_audio_runtime(monkeypatch):
    app = create_app()
    client = TestClient(app)

    assert not hasattr(app.state, "echo_save_status_provider")
    assert not hasattr(app.state, "echo_sessions_provider")
    assert not hasattr(app.state, "echo_session_provider")

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "echo router fallback must not touch filesystem, ASR/TTS/SBV2, WebSocket, or LLM runtime"
        )

    monkeypatch.setattr(main.os, "listdir", forbidden)
    monkeypatch.setattr(main.os, "stat", forbidden)
    monkeypatch.setattr(main.os.path, "isfile", forbidden)
    monkeypatch.setattr(main, "voice_status", forbidden)
    monkeypatch.setattr(main, "_resolve_asr_runtime_config", forbidden)
    monkeypatch.setattr(main, "_tts_engine_registry", object(), raising=False)
    monkeypatch.setattr(main, "_model_manager", object(), raising=False)
    monkeypatch.setattr(main.requests, "get", forbidden)
    monkeypatch.setattr(main, "echo_save_status_payload", forbidden)
    monkeypatch.setattr(main, "echo_sessions_payload", forbidden)
    monkeypatch.setattr(main, "echo_session_payload", forbidden)

    assert client.get("/echo/save-status").json() == default_echo_save_status_payload()
    assert client.get("/echo/sessions").json() == {"files": []}
    missing = client.get("/echo/sessions/missing-session.wav")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "ファイルが見つかりません"}


def test_main_app_registers_echo_providers_as_callables():
    assert callable(main.app.state.echo_save_status_provider)
    assert main.app.state.echo_save_status_provider is main.echo_save_status_payload
    assert callable(main.app.state.echo_sessions_provider)
    assert main.app.state.echo_sessions_provider is main.echo_sessions_payload
    assert callable(main.app.state.echo_session_provider)
    assert main.app.state.echo_session_provider is main.echo_session_payload


def test_main_app_echo_routes_use_provider_backed_existing_shapes(monkeypatch):
    save_payload = {
        "saving": True,
        "count": 1,
        "session_ids": ["session-1"],
        "minutes_generating_count": 1,
        "minutes_generating_session_ids": ["session-2"],
    }
    sessions_payload = {
        "files": [
            {
                "name": "session-1.md",
                "size": 123,
                "mtime": "2026-05-09 00:00",
                "type": "md",
                "group_key": "session-1",
            }
        ]
    }

    monkeypatch.setattr(
        main.app.state,
        "echo_save_status_provider",
        lambda: save_payload,
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "echo_sessions_provider",
        lambda: sessions_payload,
        raising=False,
    )

    client = TestClient(main.app)

    save_status = client.get("/echo/save-status")
    sessions = client.get("/echo/sessions")

    assert save_status.status_code == 200
    assert set(save_status.json()) == {
        "saving",
        "count",
        "session_ids",
        "minutes_generating_count",
        "minutes_generating_session_ids",
    }
    assert save_status.json() == save_payload
    assert sessions.status_code == 200
    assert set(sessions.json()) == {"files"}
    assert sessions.json() == sessions_payload
