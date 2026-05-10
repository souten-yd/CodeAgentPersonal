from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_API = ROOT / "web" / "js" / "lumen_api.js"
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_lumen_submit_payload_is_chat_only_and_sanitized():
    source = read(LUMEN_API)
    assert "clean.mode = 'chat'" in source or 'clean.mode = "chat"' in source
    assert "mode: 'task'" not in source
    assert 'mode: "task"' not in source
    assert "legacy_task" not in source
    for key in [
        "approved_tasks",
        "recommended_model",
        "auto_select_option",
        "auto_skill_generation",
    ]:
        assert key in source
        assert f"delete clean[key]" in source


def test_lumen_payload_contains_tool_search_location_and_budgets():
    source = read(LUMEN_JS)
    required_tokens = [
        "mode: 'chat'",
        "tool_policy",
        "search_policy",
        "location",
        "search_budget",
        "weather_budget",
        "news_budget",
        "chat_history",
    ]
    for token in required_tokens:
        assert token in source


def test_lumen_payload_forbidden_task_fields_not_built_by_lumen_module():
    source = read(LUMEN_JS)
    for key in [
        "approved_tasks",
        "recommended_model",
        "auto_select_option",
        "auto_skill_generation",
        "mode: 'task'",
        'mode: "task"',
    ]:
        assert key not in source
