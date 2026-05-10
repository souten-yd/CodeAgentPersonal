import json
import subprocess
from pathlib import Path

from app.lumen.tools import LumenToolResult, compress_lumen_tool_results_for_llm


ROOT = Path(__file__).resolve().parents[1]
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"


def run_lumen(expression: str) -> str:
    script = f"""
global.window = {{ LumenTools: {{ init() {{}} }} }};
global.document = {{ readyState: 'complete', addEventListener() {{}} }};
require({json.dumps(str(LUMEN_JS))});
const result = {expression};
process.stdout.write(String(result));
"""
    return subprocess.check_output(["node", "-e", script], text=True)


def test_news_context_forbids_json_dict_schema_and_raw_keys():
    context = compress_lumen_tool_results_for_llm(
        [LumenToolResult(tool="news", ok=True, content="1. 見出しA", metadata={"item_count": 1})]
    )

    assert "Do not answer in JSON" in context
    assert "Python dict" in context
    assert "raw object" in context
    assert "summary_title, news_topics, points" in context
    assert "natural Japanese prose" in context
    assert "3-5 concise bullet points" in context
    assert "Use only the provided news context" in context


def test_format_assistant_output_rewrites_single_quote_python_dict_news_output():
    raw = "{'summary_title': 'ニュース概要', 'news_topics': [{'title': '見出しA', 'points': ['要点A']}, {'title': '見出しB'}]}"
    output = run_lumen(f"window.Lumen.formatAssistantOutput({json.dumps(raw)})")

    assert not output.startswith("{'summary_title'")
    assert "summary_title" not in output
    assert "news_topics" not in output
    assert "ニュース概要" in output
    assert "- 見出しA" in output
    assert "- 見出しB" in output
