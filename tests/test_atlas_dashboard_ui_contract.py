from pathlib import Path
import re

from tests.helpers.ui_contract import load_ui_contract_text

ROOT = Path(__file__).resolve().parents[1]
UI = load_ui_contract_text()
HTML = (ROOT / "ui.html").read_text(encoding="utf-8")
ATLAS_API_JS = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")
ATLAS_DASHBOARD_JS = (ROOT / "web" / "js" / "atlas_dashboard.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
ASSET_VERSION = "atlas-dashboard-14c"


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
        'id="atlas-json-panel"',
    ):
        assert token in block


def test_fallback_planpool_note_and_stale_recovery_warning_contract() -> None:
    block = atlas_block()
    assert 'id="atlas-fallback-planpool-note"' in block
    assert '現在のCreate Planは内部fallback PlanPoolを生成します。実Planner連携は次段階で追加予定です。' in block
    assert 'id="atlas-warning-card"' in block
    assert '前回のRun状態が見つかりませんでした。PlanPoolは復元できます。必要ならStart Dry-runを再実行してください。' in block


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
