from pathlib import Path

def test_no_level1_execution_endpoint_in_vue_or_js():
    files=['web/atlas-next/src/components/Level1ReadinessPanel.vue','web/js/atlas_pipeline_api.js','web/js/atlas_dashboard.js']
    for f in files:
        t=Path(f).read_text(encoding='utf-8').lower()
        assert '/api/atlas/level1/execute' not in t
