from pathlib import Path

def test_handoff_ui_contract_chain():
    ui = Path('ui.html').read_text()
    js = Path('web/js/atlas_dashboard.js').read_text()
    api = Path('web/js/atlas_pipeline_api.js').read_text()
    assert 'atlas-verification-recommendation-handoff-btn' in ui
    assert 'atlas-verification-recommendation-handoff-summary' in ui
    assert 'atlas-verification-recommendation-handoff-result' in ui
    assert 'atlas-dashboard-36' in ui
    assert 'getVerificationRecommendationHandoff(payload)' in api
    assert '/api/atlas/repo-context/verification-recommendation-handoff' in api
    assert 'queryVerificationRecommendationHandoffFromUI' in js
    assert 'payload.plan_pool = currentPlanPoolPayload()' in js
    assert 'payload.verification_recommendation = state.verificationRecommendation?.data || state.verificationRecommendation || {}' in js
