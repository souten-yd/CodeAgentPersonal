from pathlib import Path

from tests.helpers.ui_contract import load_ui_contract_text

ROOT = Path(__file__).resolve().parents[1]
UI = load_ui_contract_text()
HTML = (ROOT / "ui.html").read_text(encoding="utf-8")
ATLAS_API_JS = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")
ATLAS_DASHBOARD_JS = (ROOT / "web" / "js" / "atlas_dashboard.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")


def atlas_block() -> str:
    return HTML.split("<!-- ATLAS MODE -->", 1)[1].split('<div class="agent-col mob-hidden"', 1)[0]


def test_atlas_dashboard_root_and_goal_composer_exist() -> None:
    block = atlas_block()
    assert 'id="atlas-dashboard"' in block
    assert 'class="atlas-dashboard"' in block
    assert 'id="atlas-goal-input"' in block
    assert 'Atlasに進めたい開発内容を書いてください。例: Atlasの進捗UIを改善する' in block
    assert 'id="atlas-create-plan-btn"' in block
    assert 'Create Plan' in block
    assert 'id="atlas-start-dry-run-btn"' in block
    assert 'Start Dry-run' in block


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
        'id="atlas-details-drawer"',
        'id="atlas-markdown-panel"',
        'id="atlas-events-panel"',
        'id="atlas-json-panel"',
    ):
        assert token in block


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


def test_mobile_overflow_guard_classes_and_css_exist() -> None:
    for token in (
        ".atlas-dashboard{width:100%;max-width:100%;min-width:0;overflow-x:hidden",
        ".atlas-status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr))",
        ".atlas-button-row{display:flex;gap:8px;flex-wrap:wrap",
        ".atlas-log-panel{max-width:100%;overflow-x:auto",
        "@media(max-width:768px){.atlas-dashboard",
        ".atlas-goal-input,.atlas-button-row button{width:100%}",
    ):
        assert token in CSS


def test_dashboard_scripts_are_loaded_after_core_assets() -> None:
    assert '<script src="/static/js/atlas_pipeline_api.js"></script>' in HTML
    assert '<script src="/static/js/atlas_dashboard.js"></script>' in HTML
    assert "AtlasPipelineAPI" in ATLAS_API_JS
    assert "AtlasDashboard" in ATLAS_DASHBOARD_JS
