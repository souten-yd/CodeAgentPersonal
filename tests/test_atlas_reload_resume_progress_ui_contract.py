from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")
API = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_pipeline_events_api_supports_progress_replay_cursor():
    body = _slice(API, "getPipelineEvents(poolId, runId, workspaceId, afterSequence)", "getRecoveryLatest(workspaceId)")

    assert "after_sequence: afterSequence" in body
    assert "/api/atlas/pipeline/events/" in body


def test_restore_latest_run_replays_server_progress_state():
    body = _slice(PANEL, "async function restoreLatestRun(poolId)", "async function restoreLatestAutonomousRun(poolId)")

    assert "await restoreRuntimeProgressReplay(poolId, runtime)" in body
    assert "renderRuntimeStatusPanel(runtime)" in body


def test_restore_does_not_show_completed_summary_while_run_is_active():
    # Returning to Atlas mid-run must not render a stale "completed" pipeline summary; it is gated on
    # the authoritative orchestrator status not being "running".
    body = _slice(PANEL, "async function restoreLatestRun(poolId)", "async function restoreLatestAutonomousRun(poolId)")
    assert "const autoStatus = await restoreLatestAutonomousRun(poolId)" in body
    assert "'running'" in body
    assert "hasAutopilotResult && !runActive" in body


def test_plan_generation_in_flight_is_tracked_around_create_pool():
    # createPlanPool must set/clear the in-flight flag so a tab switch mid-planning can tell that
    # generation is still running (the pool isn't persisted until planning finishes).
    body = _slice(PANEL, "    setBusy(true);\n    // Mark planning in flight", "    if (!resp.ok) {")
    assert "state.planGenerationInFlight = true;" in body
    assert "} finally {" in body
    assert "state.planGenerationInFlight = false;" in body


def test_runtime_status_404_during_planning_is_not_terminal_failure():
    # While planning is in flight, a plan_pool_not_found runtime-status must render a benign
    # "planning" state, not a terminal retry/revise/cancel panel.
    body = _slice(PANEL, "async function loadRuntimeStatus(poolId)", "function renderRuntimeStatusPanel(view, block)")
    assert "state.planGenerationInFlight && /plan_pool_not_found/i.test(String(errText))" in body
    assert "phase: 'planning'" in body
    assert "status: 'running'" in body
    # The terminal failure path is still present for the non-planning case.
    assert "next_actions: ['retry', 'revise plan', 'cancel']" in body


def test_restore_catch_skips_terminal_failure_while_planning():
    body = _slice(PANEL, "async function restoreLatestRun(poolId)", "async function restoreLatestAutonomousRun(poolId)")
    assert "if (!state.planGenerationInFlight) {" in body


def test_runtime_progress_replay_uses_server_authoritative_events_and_local_hints():
    body = _slice(PANEL, "async function restoreRuntimeProgressReplay(poolId, runtime)", "function bindInputs()")

    assert "getPipelineEvents(poolId, runId, workspaceId(), afterSequence)" in body
    assert "progress_events" in body
    assert "latest_progress" in body
    assert "STORAGE_LAST_RUN_ID_KEY" in body
    assert "STORAGE_LAST_EVENT_SEQUENCE_KEY" in body
    assert "applyRuntimeProgressEvent" in body


def test_runtime_progress_event_updates_indicator_and_status_panel():
    body = _slice(PANEL, "function applyRuntimeProgressEvent(event, poolId)", "async function restoreRuntimeProgressReplay")

    assert "atlas:llm-progress" in body
    assert "tokens_total" in body
    assert "renderRuntimeStatusPanel(runtimeStatusPayload" in body
    assert "restored_progress: true" in body
    assert "server progress replay" in body


def test_atlas_activation_fallback_restores_run_from_pool_hint():
    body = _slice(PANEL, "function activate()", "function deactivate()")

    assert "localStorage.getItem(STORAGE_LAST_POOL_ID_KEY)" in body
    assert "restoreLatestRun(lastPoolId)" in body


def test_runtime_panel_has_non_empty_restored_planning_state():
    body = _slice(PANEL, "function renderRuntimeStatusPanel(view, block)", "function renderPipelineSummary(block, d)")

    assert "phase === 'planning'" in body
    assert "view.restored_progress && view.message" in body
    assert "復元:" in body
