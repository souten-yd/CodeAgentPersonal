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


def test_no_public_level1_execute_route_exposed_in_scanned_surfaces():
    forbidden = ['/api/atlas/level1/execute', '/api/atlas/execute']
    for f in SAFETY_FILES:
        text = _read(f)
        for token in forbidden:
            assert token not in text, f'{token} present in {f}'


def test_no_unsafe_shell_execution_primitives_in_scanned_surfaces():
    forbidden = ['os.system']
    for f in SAFETY_FILES:
        text = _read(f)
        for token in forbidden:
            assert token not in text, f'{token} present in {f}'
