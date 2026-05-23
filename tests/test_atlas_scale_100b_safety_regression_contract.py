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


def _read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8').lower()


def test_readiness_endpoint_get_only_contract_tokens():
    vue = _read('web/atlas-next/src/api/atlasClient.ts')
    assert '/api/atlas/level1/readiness' in vue
    assert 'method: "post"' not in vue
    assert 'method: "put"' not in vue
    assert 'method: "patch"' not in vue
    assert 'method: "delete"' not in vue


def test_scanned_surfaces_do_not_expose_public_execute_routes():
    forbidden = ['/api/atlas/level1/execute', '/api/atlas/execute']
    for f in SAFETY_FILES:
        text = _read(f)
        for token in forbidden:
            assert token not in text, f'{token} present in {f}'


def test_execute_all_and_auto_continue_not_enabled_wording():
    text = _read('web/js/atlas_dashboard.js')
    assert 'auto-continue / no execute-all' in text
    assert 'execute-all enabled' not in text
    assert 'auto-continue enabled' not in text
    assert 'autonomous execution enabled' not in text
