from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")
APIPY = (ROOT / "app" / "api" / "atlas_pipeline.py").read_text(encoding="utf-8")


def test_plan_history_restore_passes_allow_reuse():
    # Opening a pool from Plan History must request the reuse/reset controls.
    body = PANEL[PANEL.index("async function restorePlanPool"):PANEL.index("function renderWorkbenchFlow")]
    assert "renderPlanPoolMarkdown(poolId, { allowReuse: true })" in body


def test_allow_reuse_takes_precedence_over_plain_approval_prompt():
    # From Plan History a previously-failed/blocked plan must offer reset+regenerate, not just the
    # plain approval prompt — so the allowReuse branch must come BEFORE the approval_required branch.
    reuse_idx = PANEL.index("} else if (opts.allowReuse) {")
    approval_idx = PANEL.index("} else if (poolStatus === 'approval_required') {")
    assert reuse_idx < approval_idx


def test_reuse_resets_execution_before_running():
    # Re-running from history clears prior execution state first so a failed/applied item does not
    # block regeneration; reset must happen before the approve+run.
    body = PANEL[PANEL.index("async function reuseAndRunPipeline"):PANEL.index("function showRevisionIndicator")]
    reset_idx = body.index("resetPoolExecution(poolId")
    run_idx = body.index("approveAndRunPipeline(poolId)")
    assert reset_idx < run_idx


def test_reset_execution_clears_failure_and_revision_state_server_side():
    # The server reset must clear failed/blocked/completed flags, per-item execution metadata,
    # retry_count, and the plan_revision_required gate so generation restarts cleanly.
    body = APIPY[APIPY.index("def reset_pool_execution"):APIPY.index("class AtlasRevisionRequest")]
    assert "pool.failed_item_ids = []" in body
    assert "pool.blocked_item_ids = []" in body
    assert '"plan_revision_required"' in body
    assert "item.retry_count = 0" in body
    assert 'item.status = "queued"' in body
    assert '"patch_proposal"' in body
