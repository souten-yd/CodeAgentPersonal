import json
import subprocess
from pathlib import Path

from app.services.lumen_runtime import sanitize_lumen_chat_history

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "app" / "lumen" / "tools.py"
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"
RUNTIME = ROOT / "app" / "services" / "lumen_runtime.py"


def _run_lumen(expression: str) -> str:
    script = f"""
global.window = {{ LumenTools: {{ init() {{}} }} }};
global.document = {{ readyState: 'complete', addEventListener() {{}} }};
require({json.dumps(str(LUMEN_JS))});
const result = {expression};
process.stdout.write(String(result));
"""
    return subprocess.check_output(["node", "-e", script], text=True)


def test_news_prompt_forbids_json_dict_raw_object_and_schema_keys():
    source = TOOLS.read_text(encoding="utf-8")
    assert "Python dict" in source
    assert "raw object" in source
    for key in ["trump_news_summary", "summary_title", "news_topics", "points", "details"]:
        assert key in source


def test_formatter_handles_trump_news_summary_json_without_raw_json():
    raw = json.dumps(
        {
            "summary_title": "トランプ大統領関連ニュースの概要です。",
            "trump_news_summary": [
                {"topic": "中東情勢（イラン関連）", "details": "回答について述べています。"},
                {"headline": "国際紛争・停戦", "points": ["3日間停戦について発表しています。"]},
            ],
        },
        ensure_ascii=False,
    )
    output = _run_lumen(f"window.Lumen.formatAssistantOutput({json.dumps(raw)})")
    assert output.startswith("トランプ大統領関連ニュースの概要です。")
    assert "- 中東情勢（イラン関連）: 回答について述べています。" in output
    assert "trump_news_summary" not in output
    assert not output.startswith("{")


def test_json_only_assistant_history_is_sanitized():
    source = RUNTIME.read_text(encoding="utf-8")
    assert "BAD_ASSISTANT_HISTORY_PATTERNS" in source
    history = [
        {"role": "user", "text": "ニュース"},
        {"role": "assistant", "text": "以降、JSON形式のみで出力します"},
        {"role": "assistant", "content": "自然文です"},
    ]
    assert sanitize_lumen_chat_history(history) == [
        {"role": "user", "text": "ニュース", "content": "ニュース"},
        {"role": "assistant", "text": "自然文です", "content": "自然文です"},
    ]
