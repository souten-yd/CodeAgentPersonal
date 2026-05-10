import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def tool_result_branch(source: str) -> str:
    match = re.search(
        r"else if \(event\.type === 'tool_result'\) \{(?P<body>.*?)\n    \} else if \(event\.type === 'chat_step'",
        source,
        re.S,
    )
    assert match, "tool_result branch should remain explicit in handleJobEvent"
    return match.group("body")


def run_lumen_script(script_body: str) -> dict:
    script = f"""
global.window = {{
  LumenTools: {{
    unwrapToolPayload(event) {{ return event.result || event.data || event; }},
    renderToolResult() {{ throw new Error('renderToolResult must not be used by the chat tool_result path'); }},
    init() {{}},
  }},
}};
global.document = {{
  readyState: 'loading',
  addEventListener() {{}},
  getElementById() {{ return null; }},
}};
const messages = [];
const progress = [];
global.addMsg = (role, text) => messages.push({{ role, text }});
global.setCard = (_card, patch) => progress.push(patch.action || patch.label || '');
require({json.dumps(str(LUMEN_JS))});
{script_body}
"""
    output = subprocess.check_output(["node", "-e", script], text=True)
    return json.loads(output)


def test_lumen_js_defines_tool_result_step_helper_and_routes_without_system_cards():
    source = read(LUMEN_JS)
    branch = tool_result_branch(source)

    assert "function rememberToolResultStep(state, event)" in source
    assert "rememberToolResultStep(state, event);" in branch
    assert "attachToolResult(state.steps, event)" in branch
    assert "renderSystemMessage" not in branch
    assert "renderToolResult" not in branch
    assert "addMsg('system', renderToolResult" not in source
    assert 'addMsg("system", renderToolResult' not in source


# Weather, News, and Search tool_result events may arrive without a prior tool_call.
# They must still be retained in state.steps while avoiding normal chat/system messages.
def test_weather_news_and_search_tool_results_are_saved_to_steps_without_chat_messages():
    result = run_lumen_script(
        """
const state = { steps: [], progressCard: {} };
window.Lumen.handleJobEvent({ type: 'tool_result', tool: 'weather', metadata: { location: { name: '横浜市' } } }, state);
window.Lumen.handleJobEvent({ type: 'tool_result', tool: 'news', metadata: { item_count: 2 } }, state);
window.Lumen.handleJobEvent({ type: 'tool_result', tool: 'search', item_count: 3, items: [{ title: 'A' }] }, state);
process.stdout.write(JSON.stringify({ steps: state.steps, messages, progress }));
"""
    )

    tools = [step["tool"] for step in result["steps"]]
    assert tools == ["weather", "news", "search"]
    assert all(step["type"] == "tool_result" for step in result["steps"])
    assert [step["action"] for step in result["steps"]] == ["weather", "news", "search"]
    assert [step["label"] for step in result["steps"]] == ["weather result", "news result", "search result"]
    assert result["messages"] == []
    assert result["progress"] == ["天気情報を取得しました", "ニュース情報を取得しました", "検索結果 3件"]


def test_search_zero_count_tool_result_is_saved_and_only_updates_progress():
    result = run_lumen_script(
        """
const state = { steps: [], progressCard: {} };
window.Lumen.handleJobEvent({ type: 'tool_result', tool: 'search', metadata: { item_count: 0, results: [] } }, state);
process.stdout.write(JSON.stringify({ steps: state.steps, messages, progress }));
"""
    )

    assert len(result["steps"]) == 1
    assert result["steps"][0]["type"] == "tool_result"
    assert result["steps"][0]["tool"] == "search"
    assert result["messages"] == []
    assert result["progress"] == ["検索結果なし"]


def test_finish_job_uses_existing_steps_renderers_and_no_one_line_tools_history():
    source = read(LUMEN_JS)

    assert "if (state?.steps?.length)" in source
    assert "addStepsBlock(state.steps)" in source
    assert "renderStepsToOutput(state.steps)" in source
    assert "TOOLS" not in source
    assert "toolHistory" not in source
    assert "tool_history" not in source
