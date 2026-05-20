from pathlib import Path


def test_ui_chain_contract():
    """Runtime-chain contract for Context Refresh v2 UI wiring.

    Broken case coverage:
    - Fails if API helper is missing.
    - Fails if helper exists but is outside AtlasPipelineAPI object.
    - Fails if dashboard references unexposed helper.
    - Fails if impact_map is omitted from payload.
    - Fails if binding is outside IIFE.
    """
    html = Path('ui.html').read_text(encoding='utf-8')
    api = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')

    assert 'atlas-context-refresh-v2-btn' in html
    assert 'atlas-context-refresh-v2-summary' in html
    assert 'atlas-context-refresh-v2-result' in html
    assert 'atlas-dashboard-34' in html
    assert 'type="module"' not in html

    assert 'getContextRefreshV2(payload)' in api
    assert '/api/atlas/context-refresh/v2' in api
    assert "method: 'POST'" in api
    assert 'body: JSON.stringify(payload || {})' in api
    helper_i = api.index('getContextRefreshV2(payload)')
    assign_i = api.index('root.AtlasPipelineAPI = AtlasPipelineAPI;')
    iife_end_api = api.rfind('})();')
    assert helper_i < assign_i
    assert helper_i < iife_end_api
    assert 'import ' not in api and 'export ' not in api

    assert 'state.contextRefreshV2' in dash
    assert 'renderContextRefreshV2Panel' in dash
    assert 'queryContextRefreshV2FromUI' in dash
    assert 'root.AtlasPipelineAPI?.getContextRefreshV2' in dash
    assert "addEventListener('click', queryContextRefreshV2FromUI)" in dash
    assert 'payload.plan_pool = currentPlanPoolPayload();' in dash
    assert 'payload.impact_map = state.planItemImpactMap?.data || state.planItemImpactMap || {}' in dash
    assert 'response?.data || response || {}' in dash
    assert 'project_path' in dash

    iife_end_dash = dash.rfind('})();')
    query_i = dash.index('async function queryContextRefreshV2FromUI')
    bind_i = dash.index("addEventListener('click', queryContextRefreshV2FromUI)")
    assert query_i < iife_end_dash
    assert bind_i < iife_end_dash
    assert 'context-refresh-v2' not in dash[iife_end_dash:]
    assert 'import ' not in dash and 'export ' not in dash
