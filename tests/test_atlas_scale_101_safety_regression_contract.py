from pathlib import Path

READINESS_SURFACES = [
    'web/atlas-next/src/components/Level1ReadinessPanel.vue',
    'web/atlas-next/src/api/atlasClient.ts',
]

def test_no_level1_execute_route_in_readiness_surfaces():
    for f in READINESS_SURFACES:
        text=Path(f).read_text(encoding='utf-8')
        assert '/api/atlas/level1/execute' not in text

def test_no_storage_upload_or_backend_mutation_terms_in_readiness_panel():
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    for token in ['upload', 'stored.*backend', 'imported.*backend']:
        assert token not in t

def test_readiness_surfaces_keep_os_system_absent():
    for f in READINESS_SURFACES:
        text=Path(f).read_text(encoding='utf-8')
        assert 'os.system' not in text
