from pathlib import Path

from app.services import lumen_runtime

RUNTIME_PATH = Path("app/services/lumen_runtime.py")


def test_lumen_runtime_service_exists_and_exports_boundaries():
    assert RUNTIME_PATH.exists()
    assert callable(lumen_runtime.submit_lumen_job_service)
    assert callable(lumen_runtime.run_lumen_job_background_service)
    assert callable(lumen_runtime.build_lumen_tool_status)
    assert callable(lumen_runtime.run_lumen_weather_direct)
    assert callable(lumen_runtime.run_lumen_news_direct)


def test_lumen_runtime_is_chat_only_and_avoids_removed_prompt_fragments():
    text = RUNTIME_PATH.read_text(encoding="utf-8")
    assert 'mode == "task"' not in text
    assert "run_task_mode_stream" not in text
    assert "approved_tasks" not in text
    assert "JSON形式で出力" not in text
    assert "options_prompt" not in text


def test_lumen_runtime_does_not_import_echo_asr_tts_sbv2():
    text = RUNTIME_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ["app.echo", "app.asr", "app.tts", "sbv2", "style_bert", "whisper"]:
        assert forbidden not in text


def test_lumen_tool_status_contract():
    payload = lumen_runtime.build_lumen_tool_status()
    assert payload["ok"] is True
    assert payload["tools"]["weather"] == {
        "enabled": True,
        "provider": "open_meteo",
        "api_key_required": False,
    }
    assert "google_news_rss" in payload["tools"]["news"]["providers"]
    assert payload["tools"]["news"]["full_text_scraping"] is False
    assert payload["tools"]["web"]["recursive_depth"] == 0
