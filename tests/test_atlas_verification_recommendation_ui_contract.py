from pathlib import Path

def test_ui_runtime_chain_contract_verification_recommendation():
    ui=Path('ui.html').read_text(); api=Path('web/js/atlas_pipeline_api.js').read_text(); dash=Path('web/js/atlas_dashboard.js').read_text()
    for dom in ['atlas-verification-recommendation-btn','atlas-verification-recommendation-summary','atlas-verification-recommendation-result']: assert dom in ui
    p_open=ui.index('<pre id="atlas-planner-packaging-v2-result"'); p_close=ui.index('</pre>', p_open); v=ui.index('atlas-verification-recommendation-btn'); assert p_open < p_close < v
    assert 'atlas-dashboard-35' in ui
    helper='getVerificationRecommendation(payload)'; assert helper in api and '/api/atlas/repo-context/verification-recommendation' in api and "method: 'POST'" in api and 'JSON.stringify(payload || {})' in api
    assign=api.index('root.AtlasPipelineAPI = AtlasPipelineAPI;'); hi=api.index(helper); end=api.rindex('})();'); assert hi < assign < end
    assert 'state.verificationRecommendation' in dash and 'function renderVerificationRecommendationPanel()' in dash and 'async function queryVerificationRecommendationFromUI()' in dash
    assert 'root.AtlasPipelineAPI?.getVerificationRecommendation' in dash and "addEventListener('click', queryVerificationRecommendationFromUI)" in dash
    assert 'payload.plan_pool = currentPlanPoolPayload()' in dash and 'payload.planner_packaging_v2 = state.plannerPackagingV2?.data || state.plannerPackagingV2 || {}' in dash and 'payload.planner_context_text_v2' in dash and 'response?.data || response || {}' in dash and 'project_path is required' in dash
    qi=dash.index('async function queryVerificationRecommendationFromUI()'); bi=dash.index("addEventListener('click', queryVerificationRecommendationFromUI)"); de=dash.rindex('})();'); assert qi < de and bi < de and 'queryVerificationRecommendationFromUI' not in dash[de:]
    assert 'import ' not in dash and 'export ' not in dash and 'type="module"' not in ui+api+dash
