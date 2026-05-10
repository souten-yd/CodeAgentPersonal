import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_lumen(expression: str) -> str:
    script = f"""
global.window = {{ LumenTools: {{ init() {{}} }} }};
global.document = {{ readyState: 'complete', addEventListener() {{}} }};
require({json.dumps(str(LUMEN_JS))});
const result = {expression};
process.stdout.write(String(result));
"""
    return subprocess.check_output(["node", "-e", script], text=True)


def test_lumen_has_assistant_output_formatter():
    source = read(LUMEN_JS)
    assert "function formatAssistantOutput" in source
    assert "JSON.parse(raw)" in source
    assert "parsed.summary" in source
    assert "parsed.topics" in source
    assert "addMsg('assistant', formatted)" in source


def test_summary_topics_json_is_formatted_as_natural_text():
    raw = json.dumps({"summary": "ニュース概要です。", "topics": ["項目A", {"title": "項目B", "detail": "詳細B"}]}, ensure_ascii=False)
    output = run_lumen(f"window.Lumen.formatAssistantOutput({json.dumps(raw)})")
    assert output == "ニュース概要です。\n- 項目A\n- 項目B: 詳細B"
    assert not output.startswith('{"summary"')


def test_unparseable_or_normal_text_is_unchanged():
    assert run_lumen("window.Lumen.formatAssistantOutput('通常の自然文です。')") == "通常の自然文です。"
    assert run_lumen("window.Lumen.formatAssistantOutput('{summary: invalid}')") == "{summary: invalid}"


def test_render_assistant_message_uses_formatter_before_bubble():
    script = f"""
const messages = [];
global.window = {{ LumenTools: {{ init() {{}} }} }};
global.document = {{ readyState: 'complete', addEventListener() {{}} }};
global.addMsg = (role, message) => messages.push([role, message]);
global.addToHistory = () => null;
require({json.dumps(str(LUMEN_JS))});
window.Lumen.renderAssistantMessage('{{"summary":"概要","topics":["A"]}}');
process.stdout.write(JSON.stringify(messages));
"""
    messages = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    assert messages == [["assistant", "概要\n- A"]]
