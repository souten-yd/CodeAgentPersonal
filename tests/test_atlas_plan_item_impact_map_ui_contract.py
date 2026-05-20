from pathlib import Path


def test_runtime_chain_contract():
    html = Path('ui.html').read_text(encoding='utf-8')
    api = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'atlas-plan-item-impact-map-btn' in html
    assert 'atlas-plan-item-impact-map-summary' in html
    assert 'atlas-plan-item-impact-map-result' in html
    assert 'getRepoContextPlanItemImpactMap' in api
    assert '/api/atlas/repo-context/plan-item-impact-map' in api
    assert 'state.planItemImpactMap' in dash
    assert 'renderPlanItemImpactMapPanel' in dash
    assert 'queryPlanItemImpactMapFromUI' in dash
    assert "addEventListener('click', queryPlanItemImpactMapFromUI)" in dash
    assert 'response?.data || response || {}' in dash
    assert 'project_path is required' in dash
    assert 'atlas-dashboard-29' in html
    iife_end = dash.rfind('})();')
    bind_idx = dash.find('atlas-plan-item-impact-map-btn')
    assert bind_idx != -1 and bind_idx < iife_end
    assert 'type="module"' not in html
    assert 'export ' not in dash and 'import ' not in dash
