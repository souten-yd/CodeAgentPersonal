from pathlib import Path
VUE=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_local_only_storage_still_used():
    assert 'localStorage' in VUE
    assert 'fetchLevel1ReadinessDiagnostics' in VUE
