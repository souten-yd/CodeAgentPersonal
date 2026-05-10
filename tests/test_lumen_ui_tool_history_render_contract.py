import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"
APP_CSS = ROOT / "web" / "css" / "app.css"
UI_HTML = ROOT / "ui.html"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_lumen(script_body: str, with_add_msg: bool = True) -> dict:
    add_msg = "global.addMsg = (role, message) => messages.push([role, message]);" if with_add_msg else "delete global.addMsg;"
    script = f"""
const messages = [];
const logs = [];
const progress = [];
const rows = [];
const output = {{ appendChild(row) {{ rows.push({{ className: row.className, textContent: row.textContent }}); }} }};
global.window = {{ LumenTools: {{ init() {{}}, unwrapToolPayload(event) {{ return event.result || event.data || event.metadata || event; }}, renderToolResult(event) {{ return 'CARD:' + event.tool; }} }} }};
global.document = {{
  readyState: 'complete',
  addEventListener() {{}},
  getElementById(id) {{ return ['chat-log', 'messages', 'output', 'chat'].includes(id) ? output : null; }},
  querySelector() {{ return output; }},
  createElement(tag) {{ return {{ tagName: tag.toUpperCase(), className: '', textContent: '' }}; }},
}};
{add_msg}
global.addLog = (level, scope, message) => logs.push([level, scope, message]);
global.setCard = (_card, data) => progress.push(data.action || data.label || '');
global.attachToolResult = (steps, event) => steps.push({{ attached: event.tool }});
global.playTTS = () => {{}};
require({json.dumps(str(LUMEN_JS))});
{script_body}
process.stdout.write(JSON.stringify({{ messages, logs, progress, rows }}));
"""
    return json.loads(subprocess.check_output(["node", "-e", script], text=True))


def test_render_tool_history_uses_tool_history_add_msg_role_first():
    source = read(LUMEN_JS)
    assert "addMsg('tool_history', text);" in source
    assert "document.getElementById('chat-log')" in source

    output = run_lumen("""
const state = { toolHistory: ['Weather ✓ 横浜'] };
window.Lumen.renderToolHistory(state);
""")
    assert output["messages"] == [["tool_history", "TOOLS: Weather ✓ 横浜"]]
    assert output["rows"] == []


def test_tool_history_role_is_not_rendered_as_system_card():
    source = read(UI_HTML)
    css = read(APP_CSS)
    assert "role === 'tool_history'" in source
    assert "d.className = 'msg tool_history lumen-tool-history'" in source
    assert "d.textContent = String(text || '')" in source
    assert "msg system" not in source[source.index("if (role === 'tool_history')") : source.index("const isMd", source.index("if (role === 'tool_history')"))]
    assert ".msg.tool_history," in css
    assert "background:transparent" in css
    assert "box-shadow:none" in css


def test_tool_name_from_event_checks_metadata_and_unwrapped_payload():
    source = read(LUMEN_JS)
    for token in ["event?.metadata?.tool", "event?.metadata?.intent", "result?.tool", "result?.metadata?.tool", "result?.metadata?.intent"]:
        assert token in source

    meta_tool = run_lumen("""
const state = { toolHistory: [] };
window.Lumen.rememberToolHistory(state, {type:'tool_result', metadata:{tool:'news', item_count:5}});
window.Lumen.renderToolHistory(state);
""")
    assert meta_tool["messages"] == [["tool_history", "TOOLS: News ✓ 5件"]]

    meta_intent = run_lumen("""
const state = { toolHistory: [] };
window.Lumen.rememberToolHistory(state, {type:'tool_result', metadata:{intent:'search', item_count:3}});
window.Lumen.renderToolHistory(state);
""")
    assert meta_intent["messages"] == [["tool_history", "TOOLS: Search ✓ 3件"]]

    unwrapped_tool = run_lumen("""
const state = { toolHistory: [] };
window.Lumen.rememberToolHistory(state, {type:'tool_result', result:{tool:'weather', location:{name:'横浜'}}});
window.Lumen.renderToolHistory(state);
""")
    assert unwrapped_tool["messages"] == [["tool_history", "TOOLS: Weather ✓ 横浜"]]


def test_finish_job_logs_history_after_assistant_before_rendering_and_tts():
    source = read(LUMEN_JS)
    assistant = source.index("const formattedOut = renderAssistantMessage(out);")
    log = source.index("tool_history: ${state?.toolHistory?.join(' / ') || 'none'}", assistant)
    history = source.index("renderToolHistory(state);", log)
    tts = source.index("playTTS(formattedOut, 'chat')", history)
    assert assistant < log < history < tts

    output = run_lumen("""
window.Lumen.stopPolling('job-1');
// exercise the exposed finish path via a done event is not exported, so assert source order above.
window.Lumen.renderToolHistory({toolHistory:['Search ✓ 3件']});
""")
    assert output["messages"] == [["tool_history", "TOOLS: Search ✓ 3件"]]


def test_render_tool_history_fallback_searches_common_chat_containers_without_add_msg():
    output = run_lumen("""
window.Lumen.renderToolHistory({ toolHistory: ['News ✓ 5件'] });
""", with_add_msg=False)
    assert output["messages"] == []
    assert output["rows"] == [{"className": "msg tool_history lumen-tool-history", "textContent": "TOOLS: News ✓ 5件"}]
