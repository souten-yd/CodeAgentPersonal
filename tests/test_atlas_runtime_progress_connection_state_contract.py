from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_progress_connection_state_classifier_distinguishes_live_reconnect_stale_stalled_terminal():
    body = _slice(PANEL, "function classifyRuntimeConnectionState(detail)", "function runtimeConnectionLabel")

    for token in [
        "PROGRESS_STALE_AFTER_SECONDS",
        "'reconnecting'",
        "'stale'",
        "'stalled'",
        "'terminal'",
        "'unknown'",
        "eventType.includes('stalled')",
        "eventType.includes('reconnect')",
        "eventType.endsWith('_completed')",
    ]:
        assert token in body


def test_llm_progress_line_renders_connection_state_class_and_label():
    body = _slice(PANEL, "function updateLlmProgressLine(detail)", "function clearLlmProgressLine()")

    assert "classifyRuntimeConnectionState(detail || {})" in body
    assert "line.dataset.connectionState = connectionState" in body
    assert "line.classList.add(connectionState)" in body
    assert "runtimeConnectionLabel(connectionState, detail || {})" in body
    assert "line.classList.toggle('stalled', connectionState === 'stalled')" in body


def test_runtime_panel_marks_non_live_state_and_never_leaves_empty_known_reconnect_frame():
    body = _slice(PANEL, "function renderRuntimeStatusPanel(view, block)", "function renderPipelineSummary(block, d)")

    assert "panel.dataset.atlasRuntimeConnectionState = connectionState" in body
    assert "panel.classList.add(`atlas-runtime-${connectionState}`)" in body
    assert "状態: ${runtimeConnectionLabel" in body
    assert "connectionState !== 'live'" in body
    assert "view.runtime_connection_state" in body


def test_replay_path_surfaces_reconnecting_unknown_and_replay_failure_stale():
    replay = _slice(PANEL, "async function restoreRuntimeProgressReplay(poolId, runtime)", "async function restoreLatestAutonomousRun")
    restore = _slice(PANEL, "async function restoreLatestRun(poolId)", "function progressRunIdFromRuntime")

    assert "const hasAutopilotResult" in restore
    assert "peek.data.autopilot_run_id || peek.data.run_id" in restore
    assert "Number.isFinite(Number(peek.data.processed_count))" in restore
    assert "runtime_connection_state: 'reconnecting'" in replay
    assert "Reconnecting to server progress replay" in replay
    assert "runtime_connection_state: 'unknown'" in replay
    assert "No replay progress event was returned for this run" in replay
    assert "runtime_connection_state: 'stale'" in restore
    assert "Progress replay unavailable; showing latest runtime snapshot" in restore


def test_css_exposes_distinct_indicator_and_runtime_state_classes():
    for token in [
        ".atlas-claude-llm-progress.reconnecting",
        ".atlas-claude-llm-progress.stale",
        ".atlas-claude-llm-progress.stalled",
        ".atlas-claude-llm-progress.terminal",
        ".atlas-claude-llm-progress.unknown",
        ".atlas-runtime-reconnecting",
        ".atlas-runtime-stale",
        ".atlas-runtime-stalled",
        ".atlas-runtime-terminal",
    ]:
        assert token in CSS
