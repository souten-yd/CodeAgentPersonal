from pathlib import Path

def test_ui_chain_present():
    ui=Path('ui.html').read_text(); api=Path('web/js/atlas_pipeline_api.js').read_text(); dash=Path('web/js/atlas_dashboard.js').read_text()
    assert 'atlas-planner-packaging-v2-btn' in ui and 'atlas-dashboard-32' in ui
    assert 'getPlannerPackagingV2(payload)' in api and '/api/atlas/repo-context/planner-packaging-v2' in api
    assert "body: JSON.stringify(payload || {})" in api
    assert 'state.plannerPackagingV2' in dash and 'queryPlannerPackagingV2FromUI' in dash
    assert "addEventListener('click', queryPlannerPackagingV2FromUI)" in dash
    assert 'response?.data || response || {}' in dash
