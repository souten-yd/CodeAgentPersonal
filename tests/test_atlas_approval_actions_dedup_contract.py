from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


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


def test_approval_prompt_text_has_single_canonical_renderer():
    assert JS.count("この Plan を実行しますか？（承認 / 改訂依頼 / キャンセル）") == 1
    assert JS.count("承認して実行") == 1
    assert JS.count("revise.textContent = '改訂を依頼';") == 1


def test_approval_actions_are_keyed_by_plan_identity():
    body = _function_body("planApprovalIdentity")
    for token in [
        "meta.plan_id",
        "strategic.plan_id",
        "meta.task_id",
        "meta.run_id",
        "meta.session_id",
        "meta.plan_revision_id",
        "poolId",
    ]:
        assert token in body

    prompt_body = _function_body("appendPlanActionPrompt")
    assert "node.dataset.atlasApprovalActions = 'true';" in prompt_body
    assert "node.dataset.poolId = String(poolId || '');" in prompt_body
    assert "node.dataset.planId = planKey;" in prompt_body


def test_approval_render_is_idempotent_and_under_active_plan_card():
    prompt_body = _function_body("appendPlanActionPrompt")
    assert "clearAtlasApprovalActions({ planId: planKey });" in prompt_body
    assert "clearAtlasApprovalActions({ removeAll: true });" in prompt_body
    assert "insertApprovalActionsNode(node, poolId, context && context.revisionId);" in prompt_body

    clear_body = _function_body("clearAtlasApprovalActions")
    assert "const removeAll = filter.removeAll === true;" in clear_body

    insert_body = _function_body("insertApprovalActionsNode")
    assert "[data-atlas-plan-card=\"true\"]" in insert_body
    assert "dom.transcript.insertBefore(node, activeCard.nextSibling);" in insert_body


def test_non_pending_plan_render_clears_stale_approval_actions():
    render_body = _function_body("renderPlanPoolMarkdown")
    assert "const approvalContext = { poolMeta, strategic, revisionId };" in render_body
    assert "poolStatus !== 'approval_required'" in render_body
    assert "poolMeta.clarification_required" in render_body
    assert "clarificationBlocks.length" in render_body
    assert "clearAtlasApprovalActions({ poolId });" in render_body
    assert "appendPlanActionPrompt(poolId, approvalContext);" in render_body


def test_approval_clicks_dismiss_plan_key_before_backend_action():
    prompt_body = _function_body("appendPlanActionPrompt")
    assert "state.dismissedApprovalPlanKeys.add(planKey);" in prompt_body
    assert "btn.disabled = true;" in prompt_body
    assert "dismiss();\n      approveAndRunPipeline(poolId);" in prompt_body
    assert "dismiss();\n      requestPlanRevision(poolId, note);" in prompt_body
    assert "dismiss();\n      cancelPlan(poolId);" in prompt_body
