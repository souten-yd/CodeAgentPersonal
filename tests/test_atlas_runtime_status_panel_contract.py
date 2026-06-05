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
    assert "getPlanRuntimeStatus(poolId, workspaceId)" in API
    assert "/runtime-status" in API
    assert "loadRuntimeStatus(poolId)" in JS
    assert "renderRuntimeStatusPanel(runtime" in JS


def test_approve_and_run_calls_approval_endpoint_before_patch_generation():
    body = _function_body("approveAndRunPipeline")
    assert "approvalTargets" in body
    assert "root.AtlasPipelineAPI.decideApproval" in body
    assert "plan_approval: true" in body
    assert "Approval failed before patch generation" in body
    assert "root.AtlasPipelineAPI.generatePatchProposal" in body
    assert body.index("root.AtlasPipelineAPI.decideApproval") < body.index("root.AtlasPipelineAPI.generatePatchProposal")


def test_runtime_panel_renders_required_patch_zero_states():
    body = _function_body("renderRuntimeStatusPanel")
    for token in [
        "current phase:",
        "pool_id:",
        "run_id:",
        "items:",
        "message:",
        "block reason:",
        "error:",
        "user action required:",
        "next action:",
        "Patch generation has not started",
        "Blocked by safety gate:",
    ]:
        assert token in body


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
