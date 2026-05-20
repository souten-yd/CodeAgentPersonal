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
    assert 'atlas-dashboard-27' in html
    assert 'type="module"' not in html and 'export ' not in api and 'import ' not in api
    assert 'atlas-repo-context-verification-plan-btn' in dash
