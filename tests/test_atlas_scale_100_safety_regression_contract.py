from pathlib import Path

SAFETY_FILES = [
    'web/atlas-next/src/components/Level1ReadinessPanel.vue',
    'web/atlas-next/src/api/atlasClient.ts',
    'web/js/atlas_pipeline_api.js',
    'web/js/atlas_dashboard.js',
    'app/api/atlas_pipeline.py',
    'app/atlas/level1_guarded_execution.py',
    'main.py',
    'app/server.py',
]

def test_no_level1_or_general_execute_routes_exposed_in_scanned_surfaces():
    forbidden = ['/api/atlas/level1/execute', '/api/atlas/execute']
    for f in SAFETY_FILES:
        text = Path(f).read_text(encoding='utf-8').lower()
        for token in forbidden:
            assert token not in text
