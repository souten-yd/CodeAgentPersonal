import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_TOOLS = ROOT / "web" / "js" / "lumen_tools.js"
LUMEN_JS = ROOT / "web" / "js" / "lumen.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_lumen_tools(expression: str) -> str:
    script = f"""
global.window = {{}};
require({json.dumps(str(LUMEN_TOOLS))});
const result = {expression};
process.stdout.write(String(result));
"""
    return subprocess.check_output(["node", "-e", script], text=True)


def test_search_renderer_reads_web_search_citation_and_context_shapes():
    source = read(LUMEN_TOOLS)
    for token in [
        "data.web_results",
        "data.search_results",
        "data.citations",
        "data.context_sources",
        "data.documents",
    ]:
        assert token in source

    web = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', web_results:[{title:'Web Result'}]})"
    )
    search = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', search_results:[{title:'Search Result'}]})"
    )
    citations = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', citations:[{source:'Citation Source'}]})"
    )
    context = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', context_sources:[{title:'Context Source'}]})"
    )

    assert "取得件数: 1" in web
    assert "Web Result" in web
    assert "Search Result" in search
    assert "Citation Source" in citations
    assert "Context Source" in context


def test_search_renderer_reads_count_candidates_and_hides_zero_cards():
    source = read(LUMEN_TOOLS)
    for token in ["data.item_count", "data.metadata?.item_count", "data.total_results", "data.result_count", "items.length"]:
        assert token in source

    total_results = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', total_results:2, items:[{title:'A'}]})"
    )
    result_count = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', result_count:3, items:[{title:'B'}]})"
    )
    zero = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', item_count:0, items:[]})"
    )

    assert "取得件数: 2" in total_results
    assert "取得件数: 3" in result_count
    assert zero == ""
    assert "🔎 Search" not in zero
    assert "取得件数: 0" not in zero


def test_lumen_js_empty_search_tool_result_updates_progress_without_rendering_card():
    source = read(LUMEN_JS)
    assert "event.type === 'tool_result'" in source
    assert "const tool = toolNameFromEvent(event);" in source
    assert "window.LumenTools.unwrapToolPayload(event)" in source
    assert "count === 0" in source
    assert "updateProgress(state, '検索結果なし')" in source
    assert "return;" in source
