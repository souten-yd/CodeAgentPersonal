import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_lumen(script_body: str) -> str:
    script = f"""
const messages = [];
const progress = [];
global.window = {{ LumenTools: {{ init() {{}}, unwrapToolPayload(event) {{ return event; }}, renderToolResult(event) {{ return 'CARD:' + event.tool; }} }} }};
global.document = {{ readyState: 'complete', addEventListener() {{}} }};
global.addMsg = (role, message) => messages.push([role, message]);
global.setCard = (_card, data) => progress.push(data.action || data.label || '');
global.attachToolResult = (steps, event) => steps.push({{ attached: event.tool }});
require({json.dumps(str(LUMEN_JS))});
{script_body}
process.stdout.write(JSON.stringify({{ messages, progress }}));
"""
    return subprocess.check_output(["node", "-e", script], text=True)


def test_weather_and_news_tool_results_are_hidden_user_facing_cards():
    source = read(LUMEN_JS)
    assert "const LUMEN_DEBUG_TOOL_CARDS = false" in source
    assert "function isHiddenUserFacingToolResult(event)" in source
    assert "return tool === 'weather' || tool === 'news'" in source
    assert "!LUMEN_DEBUG_TOOL_CARDS" in source
    assert "天気情報を取得しました" in source
    assert "ニュース情報を取得しました" in source


def test_weather_tool_result_updates_progress_without_rendering_system_card():
    output = json.loads(run_lumen("window.Lumen.handleJobEvent({type:'tool_result', tool:'weather'}, {steps: [], progressCard: {}});"))
    assert output["messages"] == []
    assert output["progress"] == ["天気情報を取得しました"]


def test_news_tool_result_updates_progress_without_rendering_system_card():
    output = json.loads(run_lumen("window.Lumen.handleJobEvent({type:'tool_result', tool:'news'}, {steps: [], progressCard: {}});"))
    assert output["messages"] == []
    assert output["progress"] == ["ニュース情報を取得しました"]


def test_search_zero_result_card_remains_hidden():
    source = read(LUMEN_JS)
    assert "event.tool === 'search'" in source
    assert "count === 0" in source
    assert "updateProgress(state, '検索結果なし')" in source
    output = json.loads(run_lumen("window.Lumen.handleJobEvent({type:'tool_result', tool:'search', item_count:0}, {steps: [], progressCard: {}});"))
    assert output["messages"] == []
    assert output["progress"] == ["検索結果なし"]
