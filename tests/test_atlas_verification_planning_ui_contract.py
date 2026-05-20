from pathlib import Path

def test_contract():
    html=Path('ui.html').read_text(encoding='utf-8')
    api=Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    dash=Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'atlas-repo-context-verification-plan-btn' in html
    assert 'atlas-repo-context-verification-plan-summary' in html
    assert 'atlas-repo-context-verification-plan-result' in html
    assert 'getRepoContextVerificationPlan' in api
    assert '/api/atlas/repo-context/verification-plan' in api
    assert 'atlas-dashboard-28' in html
    assert 'type="module"' not in html and 'export ' not in api and 'import ' not in api
    assert 'queryRepoContextVerificationPlanFromUI' in dash
    assert 'renderRepoContextVerificationPlanPanel' in dash
    assert "addEventListener('click', queryRepoContextVerificationPlanFromUI)" in dash
    assert 'response?.data || response || {}' in dash
    iife_end = dash.rfind('})();')
    assert iife_end > 0
    assert 'atlas-repo-context-verification-plan-btn' not in dash[iife_end:]
    bounded_retry_idx = dash.find('window.__atlasBoundedRetrySafety')
    assert bounded_retry_idx > 0
    assert 'atlas-repo-context-verification-plan-btn' not in dash[bounded_retry_idx:]
