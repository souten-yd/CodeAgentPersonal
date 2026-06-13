from pathlib import Path
import re

from tests.helpers.ui_contract import load_ui_contract_text

ROOT = Path(__file__).resolve().parents[1]
UI = load_ui_contract_text()
HTML = (ROOT / "ui.html").read_text(encoding="utf-8")
ATLAS_API_JS = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")
ATLAS_DASHBOARD_JS = (ROOT / "web" / "js" / "atlas_dashboard.js").read_text(encoding="utf-8")
ATLAS_CLAUDE_PANEL_JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")
ATLAS_PHASE_MANIFEST = (ROOT / "docs" / "atlas_automation_phase_manifest.json").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
# Per-asset cache-bust versions, kept in sync with the live <link>/<script> tags in ui.html.
# app.css and the atlas claude panel advance on their own UI-fix cadence, while the dashboard
# assets share the atlas-dashboard-* line.
APP_CSS_VERSION = "atlas-ui-fix-5"
DASHBOARD_ASSET_VERSION = "atlas-dashboard-40"


def atlas_block() -> str:
    return HTML.split("<!-- ATLAS MODE -->", 1)[1].split('<div class="agent-col mob-hidden"', 1)[0]


def test_atlas_dashboard_root_shell_and_goal_composer_exist() -> None:
    block = atlas_block()
    assert 'id="atlas-dashboard"' in block
    assert 'class="atlas-dashboard"' in block
    assert 'class="atlas-dashboard-shell plan-card"' in block
    assert 'id="atlas-goal-input"' in block
    assert '例: AtlasのPipeline進捗UIを改善し、リロード後も状態復元できるようにする' in block
    assert 'id="atlas-create-plan-btn"' in block
    assert 'Create Plan' in block
    assert 'id="atlas-start-dry-run-btn"' in block
    assert 'Start Dry-run' in block


def test_primary_actions_do_not_render_as_default_buttons() -> None:
    block = atlas_block()
    create = re.search(r'<button[^>]+id="atlas-create-plan-btn"[^>]+>', block)
    dry_run = re.search(r'<button[^>]+id="atlas-start-dry-run-btn"[^>]+>', block)
    assert create and 'class="atlas-primary-btn"' in create.group(0)
    assert dry_run and 'class="atlas-secondary-btn"' in dry_run.group(0)


def test_advanced_settings_are_collapsed_inside_details_by_default() -> None:
    block = atlas_block()
    details_start = block.rfind('<details', 0, block.index('id="atlas-details-drawer"'))
    details_tag = block[details_start:block.index('>', block.index('id="atlas-details-drawer"')) + 1]
    assert '<details' in details_tag
    assert ' open' not in details_tag
    assert 'id="atlas-advanced-settings"' in block
    assert 'data-atlas-advanced-settings="collapsed"' in block


def test_planpool_pipeline_recovery_and_details_containers_exist() -> None:
    block = atlas_block()
    for token in (
        'id="atlas-status-grid"',
        'id="atlas-plan-list"',
        'data-atlas-plan-list="true"',
        'id="atlas-pipeline-status"',
        'data-atlas-pipeline-status="true"',
        'id="atlas-current-item-card"',
        'id="atlas-recovery-banner"',
        'data-atlas-recovery-container="true"',
        'id="atlas-warning-card"',
        'data-atlas-stale-recovery-warning="true"',
        'id="atlas-details-drawer"',
        'id="atlas-markdown-panel"',
        'id="atlas-events-panel"',
        'id="atlas-questions-panel"',
        'id="atlas-json-panel"',
    ):
        assert token in block


def test_fallback_planpool_note_and_stale_recovery_warning_contract() -> None:
    block = atlas_block()
    assert 'id="atlas-fallback-planpool-note"' in block
    assert 'Plannerが利用できない場合はfallback PlanPoolを生成します。real Planner統合は段階的に有効化されます。' in block
    assert 'id="atlas-warning-card"' in block
    assert '前回のRun状態が見つかりませんでした。PlanPoolは復元できます。必要ならStart Dry-runを再実行してください。' in block



def test_advanced_settings_include_planner_mode_select() -> None:
    block = atlas_block()
    assert 'id="atlas-planner-mode"' in block
    assert '<option value="auto" selected>auto</option>' in block
    assert '<option value="real_planner">real_planner</option>' in block
    assert '<option value="fallback_only">fallback_only</option>' in block
    assert "planner_mode: $('atlas-planner-mode')?.value || 'auto'" in ATLAS_DASHBOARD_JS


def test_dashboard_displays_planner_fallback_and_clarification_states() -> None:
    assert "Planner fallback used:" in ATLAS_DASHBOARD_JS
    assert "waiting_for_clarification" in ATLAS_DASHBOARD_JS
    assert "追加確認が必要です。DetailsでPlanner questionsを確認してください。" in ATLAS_DASHBOARD_JS
    assert "lastPlanResponse" in ATLAS_DASHBOARD_JS
    assert "orchestrationSummary" in ATLAS_DASHBOARD_JS
    assert "applyOrchestrationSummary" in ATLAS_DASHBOARD_JS
    assert "requires_clarification" in ATLAS_DASHBOARD_JS

def test_dashboard_handles_pipeline_state_not_found_as_stale_recovery() -> None:
    assert "pipeline_state_not_found" in ATLAS_API_JS
    assert "pipeline_state_not_found" in ATLAS_DASHBOARD_JS
    assert "isPipelineStateNotFound" in ATLAS_DASHBOARD_JS
    assert "markStaleRecovery" in ATLAS_DASHBOARD_JS
    assert "removeStorage(storageKeys.runId)" in ATLAS_DASHBOARD_JS
    assert "showError(null)" in ATLAS_DASHBOARD_JS


def test_atlas_dashboard_uses_existing_atlas_api_only() -> None:
    for endpoint in (
        "/api/atlas/plan-pools",
        "/api/atlas/pipeline/dry-run",
        "/api/atlas/pipeline/status/",
        "/api/atlas/pipeline/events/",
        "/api/atlas/recovery/latest",
        "/api/atlas/recovery/pools/",
        "/api/atlas/continuation/latest",
        "/api/atlas/continuation/pools/",
    ):
        assert endpoint in ATLAS_API_JS
    assert "/api/task" not in ATLAS_API_JS + ATLAS_DASHBOARD_JS
    assert "/api/agent" not in ATLAS_API_JS + ATLAS_DASHBOARD_JS


def test_no_forbidden_execution_controls_in_new_dashboard() -> None:
    block = atlas_block().lower()
    visible_block = block.split('class="atlas-legacy-compat"', 1)[0]
    for forbidden in (
        "testcommand",
        "debugloop",
        "deepresearch",
        "deep research job",
        "web job",
    ):
        assert forbidden not in visible_block
    assert "start dry-run" in visible_block


def test_css_contract_contains_visual_rescue_selectors() -> None:
    for token in (
        ".atlas-dashboard",
        ".atlas-dashboard-shell",
        ".atlas-hero-card",
        ".atlas-goal-input",
        ".atlas-primary-btn",
        ".atlas-secondary-btn",
        ".atlas-status-grid",
        ".atlas-plan-item-card",
        ".atlas-progress",
        ".atlas-log-panel",
    ):
        assert token in CSS
    assert "border-radius: 999px" in CSS
    assert "min-height: 120px" in CSS
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in CSS
    assert "overflow-x: hidden" in CSS
    assert "@media (max-width: 768px)" in CSS


def test_ui_loads_cache_busted_static_assets() -> None:
    # atlas_pipeline_api.js advanced onto the atlas-ui-fix line when async plan-pool creation landed.
    assert f'<link rel="stylesheet" href="/static/css/app.css?v={APP_CSS_VERSION}">' in HTML
    assert '<script src="/static/js/atlas_pipeline_api.js?v=atlas-ui-fix-7"></script>' in HTML
    assert f'<script src="/static/js/atlas_dashboard.js?v={DASHBOARD_ASSET_VERSION}"></script>' in HTML
    assert "AtlasPipelineAPI" in ATLAS_API_JS
    assert "AtlasDashboard" in ATLAS_DASHBOARD_JS


def test_claude_panel_defaults_to_profile4_selection_without_authorizing_execution() -> None:
    assert "selectedPresetId: 'autonomous_bounded_dev'" in ATLAS_CLAUDE_PANEL_JS
    assert "Profile selection alone never starts an autonomous loop." in ATLAS_CLAUDE_PANEL_JS


def test_claude_profile_selection_has_no_preview_or_confirmation_input() -> None:
    assert 'id="atlas-claude-preview-profile-btn"' not in HTML
    assert 'id="atlas-claude-confirm-text"' not in HTML
    assert "atlas-claude-preview-profile-btn" not in ATLAS_CLAUDE_PANEL_JS
    assert "atlas-claude-confirm-text" not in ATLAS_CLAUDE_PANEL_JS
    assert "previewProfile" not in ATLAS_CLAUDE_PANEL_JS
    assert "previewAutomationProfile(" not in ATLAS_CLAUDE_PANEL_JS
    assert "confirmInput" not in ATLAS_CLAUDE_PANEL_JS


def test_claude_profile_apply_is_one_click_for_all_presets() -> None:
    snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("function updateSelectButtonState()"):
        ATLAS_CLAUDE_PANEL_JS.index("async function selectProfile()")
    ]
    assert "dom.selectBtn.disabled = !preset;" in snippet
    assert "CONFIRM_TEXT" not in snippet
    assert "profile_rank" not in snippet
    assert "rank >=" not in snippet
    assert "SELECT AUTOMATION SAFETY PROFILE" not in ATLAS_CLAUDE_PANEL_JS


def test_claude_profile_select_sends_canonical_confirmation_without_execution() -> None:
    snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("async function selectProfile()"):
        ATLAS_CLAUDE_PANEL_JS.index("function selectedEnvelopeId")
    ]
    assert "payload.confirmation_text = CONFIRM_TEXT;" in snippet
    assert "selectAutomationProfile(payload)" in snippet
    assert "startAutonomousLoopFromEnvelope" not in snippet
    assert "runAutonomousCodegen" not in snippet


def test_claude_profile_startup_does_not_auto_apply_autonomous_profile() -> None:
    snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("async function refreshPolicies()"):
        ATLAS_CLAUDE_PANEL_JS.index("async function refreshLatestProfile()")
    ]
    assert "autoApplyDefaultProfile" not in ATLAS_CLAUDE_PANEL_JS
    assert "selectAutomationProfile" not in snippet
    assert "pre_authorized_bounded_dev_envelope" not in snippet
    assert "Profile 4 Autonomous" not in ATLAS_CLAUDE_PANEL_JS
    assert "初期適用" not in ATLAS_CLAUDE_PANEL_JS


def test_claude_panel_policy_wording_keeps_backend_authoritative() -> None:
    assert "Profile selection alone never" in ATLAS_CLAUDE_PANEL_JS
    assert "requires backend workflow state, an active bounded envelope, and gates" in ATLAS_CLAUDE_PANEL_JS
    assert "Backend profile と active bounded envelope が確定し、gates が通過すると実行 intent を送信できます。" in ATLAS_CLAUDE_PANEL_JS
    assert "DOES pre-authorise the autonomous loop" not in ATLAS_CLAUDE_PANEL_JS
    assert "pre-authorise the autonomous loop" not in ATLAS_PHASE_MANIFEST
    assert "profile selection alone never starts an autonomous loop" in ATLAS_PHASE_MANIFEST
    assert "backend envelope + gates required" in HTML


def test_claude_panel_visual_contract_failure_is_actionable() -> None:
    for token in (
        "visual_contract.status=",
        "visual_missing:",
        "browser_smoke=",
        # Game repair guidance still present — routed to canvas_game_repair branch
        "requestAnimationFrame loop",
        "input handling",
        "update/render separation",
        "collision handling",
        "HUD state",
        "visible motion/color/canvas signals",
        # Contract-aware routing function
        "_visualRepairGuidanceForProfile",
        # Non-game profiles have appropriate guidance (no game concepts)
        "animated_dom_repair",
        "canvas_animation_repair",
        "static_html_repair",
    ):
        assert token in ATLAS_CLAUDE_PANEL_JS


def test_claude_panel_animated_dom_repair_guidance_does_not_mention_game_concepts() -> None:
    # Extract the animated_dom_repair branch from the routing function
    start = ATLAS_CLAUDE_PANEL_JS.index("if (repairProfile === 'animated_dom_repair')")
    end = ATLAS_CLAUDE_PANEL_JS.index("if (repairProfile === 'canvas_animation_repair')")
    animated_dom_block = ATLAS_CLAUDE_PANEL_JS[start:end]
    for forbidden in ("collision", "HUD", "game loop", "input handling"):
        assert forbidden not in animated_dom_block, f"animated_dom_repair must not mention '{forbidden}'"
    assert "transform" in animated_dom_block or "keyframes" in animated_dom_block


def test_continuation_panel_contract() -> None:
    block = atlas_block()
    assert 'id="atlas-continuation-panel"' in block
    assert 'id="atlas-continuation-prompt"' in block
    assert 'Refresh Continuation' in block
    assert 'Copy Continuation Prompt' in block
    assert 'Copy IDs' in block
    assert 'refreshContinuation' in ATLAS_DASHBOARD_JS
    assert 'copyContinuationPrompt' in ATLAS_DASHBOARD_JS
    assert 'copyAtlasIds' in ATLAS_DASHBOARD_JS
    assert 'getContinuationLatest' in ATLAS_API_JS
    assert 'getContinuationPool' in ATLAS_API_JS


def test_continuation_panel_is_inside_details() -> None:
    block = atlas_block()
    details_start = block.index('id="atlas-details-drawer"')
    details_end = block.rindex('</details>')
    panel_index = block.index('id="atlas-continuation-panel"')
    assert details_start < panel_index < details_end


def test_continuation_css_contract() -> None:
    for token in (
        ".atlas-continuation-panel",
        ".atlas-continuation-summary",
        ".atlas-continuation-prompt",
        ".atlas-copy-row",
        ".atlas-copy-status",
        "white-space: pre-wrap",
        "overflow-wrap: anywhere",
    ):
        assert token in CSS


def test_dashboard_orchestration_summary_controls_next_action_and_buttons() -> None:
    assert "state.orchestrationSummary?.next_action" in ATLAS_DASHBOARD_JS
    assert "can_start_dry_run" in ATLAS_DASHBOARD_JS
    assert "can_refresh_status" in ATLAS_DASHBOARD_JS
    assert "updateActionButtons" in ATLAS_DASHBOARD_JS
    assert "approval required before dry-run continuation" in ATLAS_DASHBOARD_JS


def test_waiting_for_clarification_uses_warning_not_error_contract() -> None:
    waiting_index = ATLAS_DASHBOARD_JS.index("waiting_for_clarification")
    nearby = ATLAS_DASHBOARD_JS[waiting_index:waiting_index + 900]
    assert "showWarning" in nearby
    assert "showError" not in nearby
    assert "atlas-questions-panel" in HTML
    assert "atlas-questions-list" in CSS


def test_claude_panel_mirrors_clarification_execution_blocker_contract() -> None:
    assert "function clarificationExecutionBlockReasons" in ATLAS_CLAUDE_PANEL_JS
    assert "pending_question_count" in ATLAS_CLAUDE_PANEL_JS
    assert "clarification_questions" in ATLAS_CLAUDE_PANEL_JS
    assert "missing_revised_plan_snapshot_after_clarification" in ATLAS_CLAUDE_PANEL_JS
    assert "missing_gate_rerun_evidence_after_clarification" in ATLAS_CLAUDE_PANEL_JS
    assert "rerun_critique_gate_after_clarification" in ATLAS_CLAUDE_PANEL_JS
    assert "rerun_safety_gate_after_clarification" in ATLAS_CLAUDE_PANEL_JS
    snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("const createdPool ="):
        ATLAS_CLAUDE_PANEL_JS.index("function appendPlanActionPrompt")
    ]
    assert "clarificationExecutionBlockReasons" in snippet
    assert "appendApprovalPrompt(poolId)" in snippet
    assert snippet.index("clarificationExecutionBlockReasons") < snippet.index("appendApprovalPrompt(poolId)")
    assert "確認回答と plan revision / gate rerun が完了するまで実行できません" in snippet
    render_snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("async function renderPlanPoolMarkdown"):
        ATLAS_CLAUDE_PANEL_JS.index("function preparePlanCardForUpsert")
    ]
    assert "const clarificationBlocks = clarificationExecutionBlockReasons(poolMeta);" in render_snippet
    # When clarification was answered but the revised plan did NOT clear the gate, the panel must
    # render an ACTIONABLE recovery prompt (revise / cancel) rather than a dead-end text message —
    # otherwise the user is stranded on a button-less plan card after answering every question.
    assert "appendClarificationRecoveryPrompt(poolId" in render_snippet
    assert render_snippet.index("clarificationBlocks.length") < render_snippet.index("poolStatus === 'approval_required'")
    assert render_snippet.index("clarificationBlocks.length") < render_snippet.index("appendPlanActionPrompt(poolId,")
    assert "Plan revised and gates rerun" in render_snippet
    assert "changed_scope_summary" in render_snippet
    assert "gate_rerun_summary" in render_snippet
    assert "allowed_paths_after_clarification" in render_snippet
    assert "item_changed_fields" in render_snippet


def test_claude_panel_clarification_recovery_prompt_offers_revise_and_cancel() -> None:
    # A clarification that was answered but whose revised plan did not clear the gate must NOT be a
    # dead end: the recovery prompt has to give the user a way forward (request revision / cancel).
    assert "function appendClarificationRecoveryPrompt" in ATLAS_CLAUDE_PANEL_JS
    snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("function appendClarificationRecoveryPrompt"):
        ATLAS_CLAUDE_PANEL_JS.index("async function renderPlanPoolMarkdown")
    ]
    assert "requestPlanRevision(poolId" in snippet
    assert "cancelPlan(poolId)" in snippet
    # Surface WHY it is blocked and the next required action so the prompt is not opaque.
    assert "next_required_user_action" in snippet
    assert "blockedReasons" in snippet


def test_claude_panel_critical_decision_prompt_offers_approve_revise_cancel() -> None:
    # When the critique gate raises a CRITICAL event the backend parks the pool in
    # waiting_for_critical_decision. The panel MUST render actionable controls for this state —
    # otherwise the plan card shows the Critic but no approve/revise/cancel buttons (a dead end).
    assert "function appendCriticalDecisionPrompt" in ATLAS_CLAUDE_PANEL_JS
    assert "function submitCriticalDecision" in ATLAS_CLAUDE_PANEL_JS
    prompt_snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("function appendCriticalDecisionPrompt"):
        ATLAS_CLAUDE_PANEL_JS.index("// Re-run an existing plan.")
    ]
    # Three actions mapping to the pool-scope /critical-decisions/decide endpoint.
    assert "submitCriticalDecision(poolId, 'approve'" in prompt_snippet
    assert "submitCriticalDecision(poolId, 'edit_scope'" in prompt_snippet
    assert "submitCriticalDecision(poolId, 'cancel'" in prompt_snippet
    # The decision must go through the dedicated critical-event API (not the plain approval API).
    assert "decideCriticalEvent" in ATLAS_CLAUDE_PANEL_JS
    # The render decision-tree must branch on waiting_for_critical_decision BEFORE approval_required,
    # so a revised plan that lands in the critical state is never left without controls.
    render_snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("async function renderPlanPoolMarkdown"):
        ATLAS_CLAUDE_PANEL_JS.index("function preparePlanCardForUpsert")
    ]
    assert "appendCriticalDecisionPrompt(poolId" in render_snippet
    assert (
        render_snippet.index("poolStatus === 'waiting_for_critical_decision'")
        < render_snippet.index("poolStatus === 'approval_required'")
    )


def test_claude_panel_renders_user_facing_clarification_issue_and_impact() -> None:
    assert "user_facing_issue_summary" in ATLAS_CLAUDE_PANEL_JS
    assert "why_it_matters" in ATLAS_CLAUDE_PANEL_JS
    assert "plan_change_summary" in ATLAS_CLAUDE_PANEL_JS
    assert "Impact:" in ATLAS_CLAUDE_PANEL_JS
    assert "Recommended:" in ATLAS_CLAUDE_PANEL_JS
    snippet = ATLAS_CLAUDE_PANEL_JS[
        ATLAS_CLAUDE_PANEL_JS.index("function appendClarificationPrompt"):
        ATLAS_CLAUDE_PANEL_JS.index("async function submitClarification")
    ]
    assert "actionBtn.disabled = true" in snippet
    assert "custom.disabled = true" in snippet
    assert snippet.index("actionBtn.disabled = true") < snippet.index("submitClarification(")


def test_claude_panel_renders_autonomous_repair_failure_summary() -> None:
    assert "function renderAutonomousFailureSummary" in ATLAS_CLAUDE_PANEL_JS
    assert "function renderAutonomousRepairPlan" in ATLAS_CLAUDE_PANEL_JS
    assert "function renderAutonomousCIFailure" in ATLAS_CLAUDE_PANEL_JS
    assert "function renderAutoMergeReadiness" in ATLAS_CLAUDE_PANEL_JS
    assert "verification_failure_summary" in ATLAS_CLAUDE_PANEL_JS
    assert "repairable verification failure" in ATLAS_CLAUDE_PANEL_JS
    assert "Bounded repair plan" in ATLAS_CLAUDE_PANEL_JS
    assert "post-repair verification required" in ATLAS_CLAUDE_PANEL_JS
    assert "CI failure evidence" in ATLAS_CLAUDE_PANEL_JS
    assert "CI bounded repair plan" in ATLAS_CLAUDE_PANEL_JS
    assert "post-CI repair verification required" in ATLAS_CLAUDE_PANEL_JS
    assert "Supervised auto-merge readiness" in ATLAS_CLAUDE_PANEL_JS
    assert "merge requires explicit future gate/manual action" in ATLAS_CLAUDE_PANEL_JS
    assert "merge_executed: false" in ATLAS_CLAUDE_PANEL_JS


def test_claude_panel_renders_practical_workbench_flow_without_ui_execution_authority() -> None:
    assert "function renderWorkbenchFlow" in ATLAS_CLAUDE_PANEL_JS
    assert "Atlas Workbench" in ATLAS_CLAUDE_PANEL_JS
    for token in (
        "Requirement input",
        "Start Atlas",
        "Plan Review",
        "Clarification / Critical Decision",
        "Execute Preview",
        "Verification / Repair",
        "Draft PR Artifact",
        "Backend workflow_state / PlanPool decide controls.",
        "Profile selection alone never starts an autonomous loop.",
        "Active envelope is required for the autonomous profile.",
        "Direct merge, remote git push, and self-apply are disabled.",
        "can_answer_clarification",
        "can_approve_critical_event",
        "can_reject_critical_event",
        "can_continue",
        "can_execute: false",
        "execute_apply_visible: false",
    ):
        assert token in ATLAS_CLAUDE_PANEL_JS
    assert "renderWorkbenchFlow(poolId, text" in ATLAS_CLAUDE_PANEL_JS
    assert "dataset.atlasWorkbenchBlock" in ATLAS_CLAUDE_PANEL_JS


def test_dashboard_supports_llm_backend_unavailable_warning_strings() -> None:
    assert "llm_backend_unavailable" in ATLAS_DASHBOARD_JS
    assert "real_planner_unavailable" in ATLAS_DASHBOARD_JS


def test_approval_summary_handles_needs_revision_count_contract() -> None:
    assert "needs_revision_count" in ATLAS_DASHBOARD_JS
    assert "needs revision:" in ATLAS_DASHBOARD_JS


def test_refresh_approvals_not_called_consecutively_contract() -> None:
    assert "await refreshApprovals();\n      await refreshApprovals();" not in ATLAS_DASHBOARD_JS
    assert "await refreshApprovals();\n        await refreshApprovals();" not in ATLAS_DASHBOARD_JS



def test_manual_safe_apply_ui_contract() -> None:
    assert "executeSafeApply" in ATLAS_DASHBOARD_JS
    assert "executeSafeApply(payload)" in ATLAS_API_JS
    assert "Manual safe apply is available only for approved low-risk items." in HTML
    assert "Safe Apply This Item" in ATLAS_DASHBOARD_JS
    assert "'+renderSafeApplyEligibility(item)+'" not in ATLAS_DASHBOARD_JS
    assert "Manual safe apply candidates" in ATLAS_DASHBOARD_JS
    assert "Item-level manual apply only. Tests and autopilot continuation are not run." in ATLAS_DASHBOARD_JS
    for forbidden in ("Apply all", "Auto apply", "Continue autopilot", "Run tests automatically"):
        assert forbidden not in HTML + ATLAS_DASHBOARD_JS


def test_manual_verification_ui_contract() -> None:
    assert "id=\"atlas-verification-panel\"" in HTML
    assert "Manual verification only" in HTML
    assert "runVerification(payload)" in ATLAS_API_JS
    assert "runVerification(itemId)" in ATLAS_DASHBOARD_JS
    for forbidden in ("Run all tests", "Auto fix", "Debug automatically", "Continue autopilot", "Run arbitrary command"):
        assert forbidden not in HTML + ATLAS_DASHBOARD_JS


def test_verification_panel_manual_contract() -> None:
    block = atlas_block()
    assert 'atlas-verification-panel' in block
    assert 'Manual verification only' in HTML
    assert 'Run Verification' in (HTML + ATLAS_DASHBOARD_JS)
    assert 'runVerification' in ATLAS_API_JS
    assert 'runVerification' in ATLAS_DASHBOARD_JS
    forbidden = ('Run all tests', 'Auto fix', 'Debug automatically', 'Continue autopilot', 'Run arbitrary command')
    merged = HTML + ATLAS_API_JS + ATLAS_DASHBOARD_JS
    for token in forbidden:
        assert token not in merged


def test_manual_debug_review_ui_contract() -> None:
    assert 'id="atlas-debug-review-panel"' in HTML
    assert 'Manual analysis only' in HTML
    assert 'runDebugReview(payload)' in ATLAS_API_JS
    assert 'runDebugReview(itemId)' in ATLAS_DASHBOARD_JS
    assert '/api/atlas/debug-review/run' in ATLAS_API_JS
    for forbidden in ("Auto fix", "Apply proposed fix", "Generate patch automatically", "Safe apply again", "Re-run verification automatically", "Continue autopilot", "Run command"):
        assert forbidden not in HTML + ATLAS_DASHBOARD_JS

def test_debug_review_panel_manual_only_contract() -> None:
    assert 'atlas-debug-review-panel' in HTML
    assert 'runDebugReview(payload)' in ATLAS_API_JS
    assert 'runDebugReview(itemId)' in ATLAS_DASHBOARD_JS
    assert 'Manual analysis only' in HTML
    assert 'Run Debug Review' in HTML + ATLAS_DASHBOARD_JS
    assert 'Patch Proposal Draft' in ATLAS_DASHBOARD_JS
    assert 'No patch proposal is generated automatically.' in ATLAS_DASHBOARD_JS
    assert 'No safe_apply or verification rerun is executed automatically.' in ATLAS_DASHBOARD_JS
    assert 'Next after failed verification' in ATLAS_DASHBOARD_JS
    for forbidden in ('Auto fix', 'Apply proposed fix', 'Re-run verification automatically', 'Continue autopilot', 'Run command'):
        assert forbidden not in HTML + ATLAS_DASHBOARD_JS

def test_patch_proposal_ui_contract() -> None:
    assert 'id="atlas-patch-proposal-panel"' in HTML
    assert 'Proposal only' in HTML
    assert 'Generate Patch Proposal' in HTML + ATLAS_DASHBOARD_JS
    assert 'generatePatchProposal(payload)' in ATLAS_API_JS
    assert 'generatePatchProposal(itemId)' in ATLAS_DASHBOARD_JS
    for forbidden in ('Apply patch', 'Auto apply', 'Safe apply now', 'Re-run verification', 'Continue autopilot', 'Run command'):
        assert forbidden not in HTML + ATLAS_DASHBOARD_JS


def test_patch_proposal_approval_ui_contract() -> None:
    assert "decidePatchProposal(payload)" in ATLAS_API_JS
    assert "decidePatchProposal(itemId, decision)" in ATLAS_DASHBOARD_JS
    assert "Approve Proposal" in (HTML + ATLAS_DASHBOARD_JS)
    assert "Reject Proposal" in (HTML + ATLAS_DASHBOARD_JS)
    assert "Needs Revision" in (HTML + ATLAS_DASHBOARD_JS)
    assert "Approval only" in (HTML + ATLAS_DASHBOARD_JS)
    assert "No PlanItem draft is created automatically" in (HTML + ATLAS_DASHBOARD_JS)
    assert "No patch, safe_apply, or verification rerun is executed automatically" in (HTML + ATLAS_DASHBOARD_JS)

    assert "status !== 'approved' && status !== 'rejected'" in ATLAS_DASHBOARD_JS
    assert "Approved. Next: create manual safe_apply PlanItem Draft manually." in ATLAS_DASHBOARD_JS
    assert "Rejected. No patch was applied." in ATLAS_DASHBOARD_JS
    for forbidden in ("Apply patch", "Auto apply", "Safe apply now", "Create draft automatically", "Re-run verification", "Continue autopilot", "Run command"):
        assert forbidden not in (HTML + ATLAS_DASHBOARD_JS)


def test_patch_proposal_planitem_draft_refreshes_approvals_contract() -> None:
    assert "await refreshPlanPool();" in ATLAS_DASHBOARD_JS
    assert "await refreshApprovals();" in ATLAS_DASHBOARD_JS
    assert "renderPatchProposalPanel();" in ATLAS_DASHBOARD_JS
    assert "render();" in ATLAS_DASHBOARD_JS


def test_patch_proposal_planitem_draft_ui_text_contract() -> None:
    assert "Create manual safe_apply PlanItem Draft" in (HTML + ATLAS_DASHBOARD_JS)
    assert "create manual safe_apply PlanItem Draft manually" in (HTML + ATLAS_DASHBOARD_JS)
    for forbidden in ("Apply patch", "Auto apply", "Safe apply now", "Create draft automatically", "Re-run verification", "Continue autopilot", "Run command"):
        assert forbidden not in (HTML + ATLAS_DASHBOARD_JS)


def test_verification_panel_shows_patch_proposal_draft_manual_only_copy() -> None:
    assert "Patch Proposal Draft" in ATLAS_DASHBOARD_JS
    assert "Manual verification only." in ATLAS_DASHBOARD_JS
    assert "DebugLoop is not started automatically." in ATLAS_DASHBOARD_JS
    for forbidden in ("Run all tests", "Auto verify", "Auto fix", "Debug automatically", "Continue autopilot", "Run arbitrary command"):
        assert forbidden not in HTML + ATLAS_DASHBOARD_JS


def test_patch_proposal_panel_manual_contract() -> None:
    assert 'id="atlas-patch-proposal-panel"' in HTML
    assert 'Generate Patch Proposal' in (HTML + ATLAS_DASHBOARD_JS)
    assert 'Patch Proposal Draft' in ATLAS_DASHBOARD_JS
    assert 'Approval only.' in ATLAS_DASHBOARD_JS
    assert 'No PlanItem draft is created automatically.' in ATLAS_DASHBOARD_JS
    assert 'No patch, safe_apply, or verification rerun is executed automatically.' in ATLAS_DASHBOARD_JS
    assert 'Next: review and approve/reject the proposal manually.' in ATLAS_DASHBOARD_JS
    for forbidden in ("Apply patch", "Auto apply", "Safe apply now", "Re-run verification", "Continue autopilot", "Run command", "Generate automatically"):
        assert forbidden not in (HTML + ATLAS_DASHBOARD_JS)

def test_patch_proposal_draft_creation_panel_contract() -> None:
    assert 'atlas-patch-proposal-panel' in HTML
    for token in (
        'Create manual safe_apply PlanItem Draft',
        'Draft creation only.',
        'No PlanItem approval is performed automatically.',
        'No safe_apply or verification rerun is executed automatically.',
        'Next: approve the draft PlanItem manually from Approval Gate.',
    ):
        assert token in ATLAS_DASHBOARD_JS or token in HTML
    for forbidden in (
        'Auto approve PlanItem', 'Apply patch', 'Auto apply', 'Safe apply now',
        'Create draft automatically', 'Re-run verification', 'Continue autopilot', 'Run command',
    ):
        assert forbidden not in (HTML + ATLAS_DASHBOARD_JS)


def test_manual_loop_checklist_contract() -> None:
    assert "Manual Loop Checklist" in HTML
    assert "Manual loop test mode." in HTML
    assert "No safe_apply, verification, or DebugReview is executed automatically." in HTML
    assert "Reload recovery should restore current pool and approval state." in HTML
    assert "Manual safe apply candidates" in (HTML + ATLAS_DASHBOARD_JS)
    assert "Patch Proposal Draft" in ATLAS_DASHBOARD_JS


def test_load_recovery_latest_refresh_contract() -> None:
    snippet = ATLAS_DASHBOARD_JS[ATLAS_DASHBOARD_JS.index('async function loadRecoveryLatest()'):ATLAS_DASHBOARD_JS.index('async function loadRecoveredPlan()')]
    assert 'await refreshStatus();' in snippet
    assert 'await refreshContinuation();' in snippet
    assert 'await refreshApprovals();' in snippet
    assert 'render();' in snippet


def test_forbidden_ui_tokens_absent_contract() -> None:
    merged = HTML + ATLAS_DASHBOARD_JS
    for forbidden in ('Auto apply', 'Auto verify', 'Auto debug', 'Continue autopilot', 'Run command', 'Apply all'):
        assert forbidden not in merged

def test_change_snapshot_ui_contract_strings_and_forbidden_controls() -> None:
    assert "Change Snapshot saved" in ATLAS_DASHBOARD_JS
    assert "Rollback is not automatic yet." in ATLAS_DASHBOARD_JS
    assert "Use this snapshot for manual restore if needed." in ATLAS_DASHBOARD_JS
    for forbidden in ("Restore now", "Rollback automatically", "Apply all", "Auto apply", "Auto verify", "Auto debug", "Run command"):
        assert forbidden not in HTML + ATLAS_DASHBOARD_JS


def test_pipeline_waiting_and_patch_proposal_guidance_copy_contract() -> None:
    for token in (
        "Pipeline paused:",
        "No ready item remains",
        "This is not a patch stage yet",
        "Patch Proposal is not generated by dry-run alone.",
        "Patch Proposal appears after failed verification and manual Debug Review.",
        "Manual loop: failed verification → Debug Review → Patch Proposal → Approval → PlanItem Draft → PlanItem Approval → manual safe_apply.",
        "Open Details / Advanced Panel",
    ):
        assert token in HTML + ATLAS_DASHBOARD_JS



def test_safe_apply_result_root_fields_visible_contract() -> None:
    for token in ("Executor workspace root", "Change Snapshot workspace root", "actual_file_changed", "changed_files", "file_results", "safe_apply_result.status", "reasons", "Restore from Snapshot", "Auto rollback is not enabled"):
        assert token in (HTML + ATLAS_DASHBOARD_JS)


def test_safe_apply_restore_workspace_and_manual_only_ui_contract() -> None:
    merged = HTML + ATLAS_DASHBOARD_JS
    for token in (
        "Executor workspace root",
        "Change Snapshot workspace root",
        "actual_file_changed",
        "changed_files",
        "Restore from Snapshot",
        "Restore is manual only",
        "Auto rollback is not enabled",
    ):
        assert token in merged
    for forbidden in (
        "Rollback automatically",
        "Auto verify",
        "Auto debug",
        "Continue autopilot",
        "Run command",
        "Apply all",
    ):
        assert forbidden not in merged
