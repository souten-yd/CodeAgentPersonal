from pathlib import Path

from tests.helpers.ui_contract import load_root_ui_html_text


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_llm_context_state_is_initialized_before_startup_paths():
    html = load_root_ui_html_text()

    state_idx = html.index("const LLM_CONTEXT_STATE")
    load_idx = html.index("addEventListener('load'")

    assert state_idx < load_idx
    assert "let _current_n_ctx_ui" not in html
    assert "Object.defineProperty(globalThis, '_current_n_ctx_ui'" in html
    assert "function getCurrentNctxUi()" in html
    assert "function setCurrentNctxUi(value)" in html


def test_init_ctx_slider_props_failure_is_non_fatal_and_stateful():
    html = load_root_ui_html_text()
    body = _slice(html, "async function initCtxSlider()", "async function applyCtxLen")

    assert "setCurrentNctxUi(curCtx)" in body
    assert "LLM_CONTEXT_STATE.propsAvailable = true" in body
    assert "catch(e)" in body
    assert "LLM_CONTEXT_STATE.propsAvailable = false" in body
    assert "LLM_CONTEXT_STATE.lastError" in body
    assert "Could not fetch llm props" in body
    assert "_current_n_ctx_ui =" not in body


def test_progress_line_updates_token_indicator_without_ctx_props():
    body = _slice(PANEL, "function updateLlmProgressLine(detail)", "function clearLlmProgressLine()")

    assert "tokens ${tokens}" in body
    assert "root.updateTokenDisplay" in body
    assert "tokenDelta" in body
    assert "maxCtx > 0" in body


def test_progress_indicator_shows_status_tokens_and_progress_age():
    body = _slice(PANEL, "function updateLlmProgressLine(detail)", "function clearLlmProgressLine()")
    # 表示(status) · token生成数 · <Ns> ago
    assert "phase || 'generating'" in body          # 表示
    assert "tokens ${tokens}" in body               # token生成数
    assert "`${ageSec}s ago`" in body               # 進捗 (last progress age)
    assert "Ans " not in body                       # the Ans timer was dropped per the requested format


def test_top_right_token_display_removed():
    html = load_root_ui_html_text()
    # The header "<n> tok" badge was removed (its updater is null-guarded).
    assert 'id="tok-display"' not in html
    assert 'id="tok-total"' not in html
