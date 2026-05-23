from pathlib import Path

def test_history_uses_local_storage_with_bounds_and_errors():
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert "HISTORY_STORAGE_KEY = 'atlas.level1.readiness.history'" in t
    assert 'HISTORY_MAX_ENTRIES = 5' in t
    assert 'localStorage.getItem' in t
    assert 'localStorage.setItem' in t
    assert 'storage quota or storage error' in t
    assert 'parse error' in t.lower()
