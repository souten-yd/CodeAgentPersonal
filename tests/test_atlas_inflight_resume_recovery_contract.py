from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")
API = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_poller_rides_through_transient_status_blips():
    # A single aborted/network/gateway status poll must NOT terminate the wait: the server is the
    # authority and may still be generating. We only give up on SUSTAINED unreachability.
    poller = _slice(API, "async pollPlanPoolUntilReady", "listPlanPools()")
    assert "UNREACHABLE_GRACE_MS" in poller
    assert "const transient =" in poller
    assert "st.status === 0" in poller
    assert "st.code === 'network_error'" in poller
    assert "st.code === 'gateway_timeout'" in poller
    # The transient branch retries within the grace window instead of returning immediately.
    assert "if (nowMs - unreachableSince < UNREACHABLE_GRACE_MS) continue;" in poller
    # No client-side deadline on generation time (still server-authoritative).
    assert "Date.now() - startTime" not in poller
    assert "plan_pool_absolute_timeout" not in poller


def test_create_plan_pool_surfaces_queued_pool_id_before_polling():
    # createPlanPool must hand the queued pool_id to onQueued BEFORE the (long) poll, so the caller
    # can persist the per-project recovery pointer even if the browser is closed mid-generation.
    body = _slice(API, "async createPlanPool(payload, onQueued)", "getPlanPoolStatus(poolId, workspaceId, projectInstanceId)")
    assert "if (typeof onQueued === 'function') { try { onQueued(data.pool_id); } catch (_) {} }" in body
    # onQueued fires before pollPlanPoolUntilReady on the same branch.
    on_queued_idx = body.index("onQueued(data.pool_id)")
    poll_idx = body.index("pollPlanPoolUntilReady(data.pool_id")
    assert on_queued_idx < poll_idx


def test_dispatch_persists_active_pool_id_at_queued_time():
    # The active_pool_id pointer must be persisted (project-scoped localStorage hint +
    # conversation meta) the moment the job is accepted, not after the poll completes.
    body = _slice(PANEL, "resp = await root.AtlasPipelineAPI.createPlanPool(", "if (!resp.ok) {")
    assert "(queuedPoolId) =>" in body
    assert "setProjectScopedHint(STORAGE_LAST_POOL_ID_KEY, queuedPoolId)" in body
    assert "{ active_pool_id: queuedPoolId }" in body


def test_dispatch_treats_transport_loss_after_accept_as_recoverable():
    # If the server accepted the job (earlyPoolId set) and the browser merely lost the connection,
    # this is NOT a creation failure — per-project recovery re-attaches on reopen.
    body = _slice(PANEL, "if (!resp.ok) {", "const poolId =")
    assert "const transportLost =" in body
    assert "if (earlyPoolId && transportLost) {" in body
    assert "PlanPool creation failed" in body  # genuine-failure path still present


def test_restore_resumes_in_flight_plan_generation():
    # Reopening the browser must re-attach to a still-generating plan and resume polling.
    assert "async function resumeInFlightPlanGeneration(poolId)" in PANEL
    helper = _slice(PANEL, "async function resumeInFlightPlanGeneration(poolId)", "async function restoreLatestRun(poolId)")
    assert "getPlanPoolStatus(poolId, workspaceId(), projectInstanceId())" in helper
    assert "status !== 'queued' && status !== 'running' && status !== 'revising'" in helper
    assert "pollPlanPoolUntilReady(poolId, workspaceId(), undefined, undefined, projectInstanceId())" in helper
    assert "renderPlanPoolMarkdown(poolId)" in helper
    # restoreLatestRun kicks it off (detached) so a reopened browser keeps tracking.
    run_body = _slice(PANEL, "async function restoreLatestRun(poolId)", "async function restoreLatestAutonomousRun(poolId)")
    assert "resumeInFlightPlanGeneration(poolId)" in run_body
