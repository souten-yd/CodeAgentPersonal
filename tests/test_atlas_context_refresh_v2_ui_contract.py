from pathlib import Path


def test_ui_chain_contract():
    html = Path('ui.html').read_text(encoding='utf-8')
    api = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'atlas-context-refresh-v2-btn' in html
    assert 'atlas-context-refresh-v2-summary' in html
    assert 'atlas-context-refresh-v2-result' in html
    assert 'getContextRefreshV2(payload)' in api
    assert '/api/atlas/context-refresh/v2' in api
    assert 'state.contextRefreshV2' in dash
    assert 'renderContextRefreshV2Panel' in dash
    assert "addEventListener('click', queryContextRefreshV2FromUI)" in dash
    assert 'response?.data || response || {}' in dash
    assert 'impact_map = state.planItemImpactMap?.data || state.planItemImpactMap || {}' in dash
    assert 'payload.plan_pool = currentPlanPoolPayload();' in dash
