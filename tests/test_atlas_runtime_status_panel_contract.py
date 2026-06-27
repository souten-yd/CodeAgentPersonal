from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")
API = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")


def _function_body(name: str) -> str:
    marker = f"function {name}"
    start = JS.index(marker)
    paren = JS.index("(", start)
    depth = 0
    close_paren = -1
    for pos in range(paren, len(JS)):
        char = JS[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_paren = pos
                break
    assert close_paren > -1
    brace = JS.index("{", close_paren)
    depth = 0
    for pos in range(brace, len(JS)):
        char = JS[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return JS[brace + 1:pos]
    raise AssertionError(f"{name} body not found")


def test_runtime_status_endpoint_is_exposed_to_panel():
    assert "getPlanRuntimeStatus(poolId, workspaceId, projectInstanceId)" in API
    assert "/runtime-status" in API
    assert "loadRuntimeStatus(poolId)" in JS
    assert "renderRuntimeStatusPanel(runtime" in JS


def test_approve_and_run_delegates_to_backend_run_api():
    body = _function_body("approveAndRunPipeline")
    assert "root.AtlasPipelineAPI.createRun" in body
    assert "watchBackendRun(poolId, runId, stages)" in body
    assert "authoritative_source: '/api/atlas/runs'" in body
    assert "root.AtlasPipelineAPI.getPlanPool" not in body
    assert "item_ids:" not in body
    assert "root.AtlasPipelineAPI.decideApproval" not in body
    assert "root.AtlasPipelineAPI.generatePatchProposal" not in body
    assert "root.AtlasPipelineAPI.runMultiItemAutopilot" not in body


def test_run_recovery_controls_prefer_run_retry_and_revise_when_run_id_exists():
    body = _function_body("appendRecoveryActions")
    assert "root.AtlasPipelineAPI.retryRun" in body
    assert "root.AtlasPipelineAPI.reviseRun" in body
    assert "approveAndRunPipeline(pid, { resume: true })" in body
    assert "requestPlanRevision(pid, note)" in body
    assert "リトライ開始に失敗しました" in body


def test_runtime_panel_renders_required_patch_zero_states():
    body = _function_body("renderRuntimeStatusPanel")
    for token in [
        "phase === 'patch_generation'",
        "Patchを生成・検証しています",
        "view.restored_progress && view.message",
        "復元:",
        "view.restored_state_rejected",
        "restore_rejected_reason",
        "状態:",
        "runtimeConnectionLabel",
        "推奨操作:",
        "Blocked by safety gate:",
        "実行中",
        "フェーズ",
        "進捗:",
        "現在:",
        "Tokens:",
        "failed_count",
        "blocked_count",
        "skipped_count",
    ]:
        assert token in body


def test_backend_run_watcher_renders_server_item_progress_and_token_indicator():
    body = _function_body("watchBackendRun")
    assert "normalizeRunItemProgress(d.item_progress, d)" in body
    assert "renderPlanSteps(stages, itemSteps)" in body
    assert "runTokenUsagePayload(d)" in body
    assert "new CustomEvent('atlas:llm-progress'" in body
    assert "tokens: tokenUsage.generated" in body
    assert "maxCtx: tokenUsage.maxCtx" in body
    assert "items_completed: d.completed_count || 0" in body
    assert "failed_count: d.failed_count || 0" in body
    assert "blocked_count: d.blocked_count || 0" in body
    assert "skipped_count: d.skipped_count || 0" in body
    assert "current_item_title: currentRunItemTitle(d, itemSteps)" in body


def test_run_item_progress_normalizer_uses_backend_status_fields_only():
    body = _function_body("normalizeRunItemProgress")
    assert "Array.isArray(itemProgress)" in body
    assert "item.status" in body
    assert "d.current_item_id" in body
    assert "d.completed_count" in body
    assert "d.failed_count" in body
    assert "d.blocked_count" in body
    assert "d.skipped_count" in body
    assert "runItemStepState(status)" in body


def test_runtime_panel_reuses_one_stage_block_for_polling():
    append_body = _function_body("appendStageBlock")
    render_body = _function_body("renderRuntimeStatusPanel")
    poll_body = _function_body("approveAndRunPipeline")

    assert "el.dataset.atlasStageBlock === 'true' && el.dataset.poolId === String(poolId)" in append_body
    assert "const panel = block || appendStageBlock(poolId);" in render_body
    assert "renderRuntimeStatusPanel(runtimeStatusPayload(poolId" in poll_body
    assert "}), stages);" in poll_body


def test_restore_failures_are_not_silently_swallowed():
    restore_body = _function_body("restoreLatestRun")
    assert "console.warn('Atlas runtime status restore failed'" in restore_body
    assert "Run status unavailable" in restore_body
    assert "endpoint=/api/atlas/plan-pools/" in restore_body


def test_project_scoped_pool_fetches_include_workspace_id():
    assert "getPlanPoolStatus(poolId, workspaceId, projectInstanceId)" in API
    assert "getPlanPool(poolId, workspaceId, projectInstanceId)" in API
    assert "query({ workspace_id: workspaceId, project_instance_id: projectInstanceId })" in API
    assert "root.AtlasPipelineAPI.getPlanPoolStatus(poolId, workspaceId(), projectInstanceId())" in JS
    assert "root.AtlasPipelineAPI.getPlanPool(poolId, workspaceId(), projectInstanceId())" in JS
