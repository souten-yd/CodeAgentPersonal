from pathlib import Path

def test_local_history_controls_and_non_execution_labels():
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    for token in ['save to local history', 'use selected history baseline', 'clear local history', 'delete', 'browser storage only']:
        assert token in t
    for word in ['execute','apply','approve','verify','rollback','retry','continue','dry-run']:
        assert f'>{word}<' not in t
