from pathlib import Path
import re

def test_handoff_helper_and_binding_positions():
    api = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    ui = Path('ui.html').read_text(encoding='utf-8')
    assert api.index('getVerificationRecommendationHandoff(payload)') < api.index('root.AtlasPipelineAPI = AtlasPipelineAPI')
    final = dash.rfind('})();')
    assert dash.index('atlas-verification-recommendation-handoff-btn') < final
    assert dash.rfind('atlas-verification-recommendation-handoff-btn') < final
    assert 'const data = response?.data || response || {};' in dash
    assert ui.index('atlas-verification-recommendation-handoff-result') > ui.index('atlas-verification-recommendation-result')
    assert ui.index('atlas-verification-recommendation-handoff-btn') < ui.index('atlas-verification-recommendation-handoff-summary') < ui.index('atlas-verification-recommendation-handoff-result')
