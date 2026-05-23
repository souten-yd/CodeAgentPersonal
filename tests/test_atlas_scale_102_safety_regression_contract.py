from pathlib import Path

SCAN_FILES = [
    'web/atlas-next/src/components/Level1ReadinessPanel.vue',
    'web/atlas-next/src/api/atlasClient.ts',
    'web/js/atlas_pipeline_api.js',
    'web/js/atlas_dashboard.js',
    'app/api/atlas_pipeline.py',
    'app/atlas/level1_guarded_execution.py',
    'main.py',
    'app/server.py',
]


def test_safety_scan_file_inventory_exists():
    for p in SCAN_FILES:
        assert Path(p).exists()


def test_readiness_import_export_surface_stays_local_only():
    vue = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()
    api = Path('web/atlas-next/src/api/atlasClient.ts').read_text()
    assert 'localStorage' in vue
    assert 'FileReader' in vue
    assert 'JSON.parse' in vue
    assert 'fetchLevel1ReadinessDiagnostics' in vue
    assert '/api/atlas/level1/readiness' in api
    for token in ['/api/atlas/level1/execute', '/dry-run/start', '/approvals/decide', '/change-snapshots/restore']:
        assert token not in vue


def test_no_eval_or_dynamic_function_in_readiness_panel():
    vue = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()
    for token in ['eval', 'new Function', 'Function(']:
        assert token not in vue
