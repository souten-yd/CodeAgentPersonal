from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_diff_uses_local_data_only_helpers():
    assert 'compareSelectedHistoryEntries' in TEXT
    assert 'compareCurrentToHistoryEntry' in TEXT
    assert 'fetchLevel1ReadinessDiagnostics' in TEXT
    assert 'local-only' in TEXT
