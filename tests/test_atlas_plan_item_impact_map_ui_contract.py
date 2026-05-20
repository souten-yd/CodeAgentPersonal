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

    # Broken-case guard: fails if UI keeps using state.currentPlanPool and sends {} plan_pool.
    assert 'state.currentPlanPool' not in dash
    assert 'function currentPlanPoolPayload()' in dash
    assert 'state.planPool?.plan_pool' in dash and 'state.planPool' in dash
    assert 'state.lastPlanResponse?.plan_pool' in dash
    assert 'payload.plan_pool = currentPlanPoolPayload();' in dash

    assert 'state.planItemImpactMap' in dash
    assert 'renderPlanItemImpactMapPanel' in dash
    assert 'queryPlanItemImpactMapFromUI' in dash
    assert "addEventListener('click', queryPlanItemImpactMapFromUI)" in dash

    # Broken-case guard: fails if API response .data unwrap is removed.
    assert 'response?.data || response || {}' in dash
    assert 'project_path is required' in dash
    assert 'atlas-dashboard-32' in html

    iife_end = dash.rfind('})();')
    query_idx = dash.find('queryPlanItemImpactMapFromUI')
    bind_idx = dash.find('atlas-plan-item-impact-map-btn')
    assert query_idx != -1 and query_idx < iife_end
    assert bind_idx != -1 and bind_idx < iife_end

    # Broken-case guard: fails if binding is appended outside the IIFE.
    after_iife = dash[iife_end + 4 :]
    assert 'atlas-plan-item-impact-map-btn' not in after_iife

    assert 'type="module"' not in html
    assert 'export ' not in dash and 'import ' not in dash
