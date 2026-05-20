from pathlib import Path


def test_planner_packaging_v2_runtime_chain_contract():
    ui = Path('ui.html').read_text()
    api = Path('web/js/atlas_pipeline_api.js').read_text()
    dash = Path('web/js/atlas_dashboard.js').read_text()

    # broken-case: fails if context-refresh-v2 pre tag is broken
    for dom_id in [
        'atlas-context-refresh-v2-btn', 'atlas-context-refresh-v2-summary', 'atlas-context-refresh-v2-result',
        'atlas-planner-packaging-v2-btn', 'atlas-planner-packaging-v2-summary', 'atlas-planner-packaging-v2-result',
    ]:
        assert dom_id in ui
    pre_open = ui.index('<pre id="atlas-context-refresh-v2-result"')
    pre_close = ui.index('</pre>', pre_open)
    planner_btn = ui.index('atlas-planner-packaging-v2-btn')
    assert pre_open < pre_close < planner_btn
    assert 'atlas-dashboard-35' in ui

    # broken-case: fails if helper missing/outside object/final iife
    helper = 'getPlannerPackagingV2(payload)'
    assert helper in api
    assert '/api/atlas/repo-context/planner-packaging-v2' in api
    assert "method: 'POST'" in api
    assert 'body: JSON.stringify(payload || {})' in api
    assign_i = api.index('root.AtlasPipelineAPI = AtlasPipelineAPI;')
    helper_i = api.index(helper)
    end_iife = api.rindex('})();')
    assert helper_i < assign_i < end_iife

    # broken-case: fails if only binding exists without real query function
    assert 'state.plannerPackagingV2' in dash
    assert 'function renderPlannerPackagingV2Panel()' in dash
    assert 'async function queryPlannerPackagingV2FromUI()' in dash
    assert 'root.AtlasPipelineAPI?.getPlannerPackagingV2' in dash
    assert "addEventListener('click', queryPlannerPackagingV2FromUI)" in dash
    assert 'payload.plan_pool = currentPlanPoolPayload()' in dash
    assert 'payload.plan_item_impact_map = state.planItemImpactMap?.data || state.planItemImpactMap || {}' in dash
    assert 'payload.context_refresh_v2 = state.contextRefreshV2?.data || state.contextRefreshV2 || {}' in dash
    assert 'response?.data || response || {}' in dash
    assert 'project_path is required' in dash
    q_i = dash.index('async function queryPlannerPackagingV2FromUI()')
    bind_i = dash.index("addEventListener('click', queryPlannerPackagingV2FromUI)")
    end_dash = dash.rindex('})();')
    assert q_i < end_dash and bind_i < end_dash
    assert 'queryPlannerPackagingV2FromUI' not in dash[end_dash:]
    assert 'type="module"' not in ui + api + dash
    assert 'import ' not in dash and 'export ' not in dash
