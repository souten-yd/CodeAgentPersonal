import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"
APP_CSS = ROOT / "web" / "css" / "app.css"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_lumen(script_body: str) -> dict:
    script = f"""
const messages = [];
const progress = [];
const rows = [];
const output = {{ appendChild(row) {{ rows.push({{ className: row.className, textContent: row.textContent }}); }} }};
global.window = {{ LumenTools: {{ init() {{}}, unwrapToolPayload(event) {{ return event.result || event.data || event.metadata || event; }}, renderToolResult(event) {{ return 'CARD:' + event.tool; }} }} }};
global.document = {{
  readyState: 'complete',
  addEventListener() {{}},
  getElementById(id) {{ return id === 'output' ? output : null; }},
  createElement(tag) {{ return {{ tagName: tag.toUpperCase(), className: '', textContent: '' }}; }},
}};
global.addMsg = (role, message) => messages.push([role, message]);
global.setCard = (_card, data) => progress.push(data.action || data.label || '');
global.attachToolResult = (steps, event) => steps.push({{ attached: event.tool }});
global.playTTS = () => {{}};
require({json.dumps(str(LUMEN_JS))});
{script_body}
process.stdout.write(JSON.stringify({{ messages, progress, rows }}));
"""
    return json.loads(subprocess.check_output(["node", "-e", script], text=True))


def test_lumen_js_has_tool_history_helpers_and_compact_css():
    source = read(LUMEN_JS)
    css = read(APP_CSS)
    assert "function rememberToolHistory(state, event)" in source
    assert "function renderToolHistory(state)" in source
    assert "toolHistory: []" in source
    assert "row.className = 'lumen-tool-history'" in source
    assert "TOOLS: ${state.toolHistory.join(' / ')}" in source
    assert ".lumen-tool-history" in css


def test_weather_tool_result_records_history_without_large_system_card():
    output = run_lumen("""
const state = { steps: [], progressCard: {} };
window.Lumen.handleJobEvent({type:'tool_result', tool:'weather', result:{location:{name:'横浜'}}}, state);
window.Lumen.renderToolHistory(state);
""")
    assert output["messages"] == []
    assert output["progress"] == ["天気情報を取得しました"]
    assert output["rows"] == [{"className": "lumen-tool-history", "textContent": "TOOLS: Weather ✓ 横浜"}]


def test_news_tool_result_records_count_without_large_system_card():
    output = run_lumen("""
const state = { steps: [], progressCard: {} };
window.Lumen.handleJobEvent({type:'tool_result', tool:'news', result:{item_count:5}}, state);
window.Lumen.renderToolHistory(state);
""")
    assert output["messages"] == []
    assert output["progress"] == ["ニュース情報を取得しました"]
    assert output["rows"] == [{"className": "lumen-tool-history", "textContent": "TOOLS: News ✓ 5件"}]


def test_search_tool_result_records_zero_count_without_large_system_card():
    output = run_lumen("""
const state = { steps: [], progressCard: {} };
window.Lumen.handleJobEvent({type:'tool_result', tool:'search', result:{item_count:0}}, state);
window.Lumen.renderToolHistory(state);
""")
    assert output["messages"] == []
    assert output["progress"] == ["検索結果なし"]
    assert output["rows"] == [{"className": "lumen-tool-history", "textContent": "TOOLS: Search 結果なし"}]


def test_assistant_finish_path_renders_tool_history_before_tts():
    source = read(LUMEN_JS)
    assistant = source.index("const formattedOut = renderAssistantMessage(out);")
    history = source.index("renderToolHistory(state);", assistant)
    tts = source.index("playTTS(formattedOut, 'chat')", history)
    assert assistant < history < tts


def test_tool_history_can_label_positive_search_count():
    output = run_lumen("""
const state = { toolHistory: [] };
window.Lumen.rememberToolHistory(state, {type:'tool_result', tool:'search', result:{item_count:3}});
window.Lumen.renderToolHistory(state);
""")
    assert output["rows"] == [{"className": "lumen-tool-history", "textContent": "TOOLS: Search ✓ 3件"}]
