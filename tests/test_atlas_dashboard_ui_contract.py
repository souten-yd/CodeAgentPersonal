from pathlib import Path
import re

from tests.helpers.ui_contract import load_ui_contract_text

ROOT = Path(__file__).resolve().parents[1]
UI = load_ui_contract_text()
HTML = (ROOT / "ui.html").read_text(encoding="utf-8")
ATLAS_API_JS = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")
ATLAS_DASHBOARD_JS = (ROOT / "web" / "js" / "atlas_dashboard.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
ASSET_VERSION = "atlas-dashboard-15"


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
        "safe_apply",
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
    assert f'<link rel="stylesheet" href="/static/css/app.css?v={ASSET_VERSION}">' in HTML
    assert f'<script src="/static/js/atlas_pipeline_api.js?v={ASSET_VERSION}"></script>' in HTML
    assert f'<script src="/static/js/atlas_dashboard.js?v={ASSET_VERSION}"></script>' in HTML
    assert "AtlasPipelineAPI" in ATLAS_API_JS
    assert "AtlasDashboard" in ATLAS_DASHBOARD_JS


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
    details_end = block.index('</details>', details_start)
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


def test_dashboard_supports_llm_backend_unavailable_warning_strings() -> None:
    assert "llm_backend_unavailable" in ATLAS_DASHBOARD_JS
    assert "real_planner_unavailable" in ATLAS_DASHBOARD_JS


def test_approval_summary_handles_needs_revision_count_contract() -> None:
    assert "needs_revision_count" in ATLAS_DASHBOARD_JS
    assert "needs revision:" in ATLAS_DASHBOARD_JS


def test_refresh_approvals_not_called_consecutively_contract() -> None:
    assert "await refreshApprovals();\n      await refreshApprovals();" not in ATLAS_DASHBOARD_JS
    assert "await refreshApprovals();\n        await refreshApprovals();" not in ATLAS_DASHBOARD_JS

