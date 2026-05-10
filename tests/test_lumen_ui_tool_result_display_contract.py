import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUMEN_TOOLS = ROOT / "web" / "js" / "lumen_tools.js"


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


def test_news_renderer_reads_top_topics_metadata_count_status_and_sources():
    source = read(LUMEN_TOOLS)
    for token in [
        "function unwrapToolPayload",
        "event?.metadata",
        "result.top_topics",
        "result.metadata?.top_topics",
        "data.overall_status",
        "data.metadata?.overall_status",
        "data.item_count ?? data.metadata?.item_count ?? items.length",
        "data.sources || data.metadata?.sources",
    ]:
        assert token in source

    output = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'news', metadata:{overall_status:'degraded', item_count:12, top_topics:[{title:'見出しA'}, {headline:'見出しB'}], sources:[{provider:'google_news_rss'}, {provider:'bbc_rss'}]}})"
    )
    assert "📰 News" in output
    assert "status: degraded" in output
    assert "取得件数: 12" in output
    assert "主なprovider: google_news_rss, bbc_rss" in output
    assert "1. 見出しA" in output
    assert "2. 見出しB" in output


def test_news_zero_item_count_is_rendered_as_failed_without_headlines():
    source = read(LUMEN_TOOLS)
    assert "Number(itemCount) === 0 ? 'failed'" in source
    assert "有効なニュース記事を取得できませんでした。" in source
    assert "推測によるニュース要約は行いません。" in source

    output = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'news', result:'ニュース取得結果', metadata:{overall_status:'ok', item_count:0, top_topics:[{title:'出してはいけない見出し'}], sources:[{provider:'rss'}]}})"
    )
    assert "📰 News" in output
    assert "status: failed" in output
    assert "取得件数: 0" in output
    assert "有効なニュース記事を取得できませんでした。" in output
    assert "推測によるニュース要約は行いません。" in output
    assert "1. 出してはいけない見出し" not in output


def test_tool_payload_unwraps_string_result_with_event_metadata():
    output = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'news', result:'plain result text', metadata:{overall_status:'degraded', item_count:1, top_topics:[{title:'文字列resultでもmetadataを読む'}], provider_status:[{provider:'rss', status:'ok', item_count:1}]}})"
    )
    assert "status: degraded" in output
    assert "取得件数: 1" in output
    assert "provider: rss: ok (1)" in output
    assert "1. 文字列resultでもmetadataを読む" in output


def test_tool_payload_unwraps_event_metadata_for_weather_details():
    output = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'weather', metadata:{location:{name:'横浜市', admin1:'神奈川県'}, current:{temperature_c:18.5, weather_text:'曇り', precipitation_probability:30}, fetched_at:'2026-05-10T00:00:00Z'}})"
    )
    assert "🌤 Weather" in output
    assert "地域: 横浜市 / 神奈川県" in output
    assert "現在: 18.5°C / 曇り" in output
    assert "降水確率: 30%" in output
    assert "取得時刻: 2026-05-10T00:00:00Z" in output


def test_weather_renderer_displays_location_not_found_error():
    output = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'weather', metadata:{ok:false, error:'location_not_found', location_hint:'横浜市南区', message:'地域が見つかりませんでした'}})"
    )
    assert "🌤 Weather" in output
    assert "取得できませんでした: location_not_found" in output
    assert "地域: 横浜市南区" in output
    assert "より広い地域名、駅名、都道府県名で再入力してください。" in output


def test_search_zero_count_and_planned_only_do_not_render_large_result_card():
    planned = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'web', metadata:{planned_only:true, item_count:0}})"
    )
    assert planned == ""

    zero = run_lumen_tools(
        "window.LumenTools.renderToolResult({type:'tool_result', tool:'search', metadata:{item_count:0, results:[]}})"
    )
    assert zero == "検索結果はありませんでした。"
    assert "🔎 Search" not in zero
    assert "取得件数: 0" not in zero
