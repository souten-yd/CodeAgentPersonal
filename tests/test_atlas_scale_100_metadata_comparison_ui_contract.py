from pathlib import Path

def test_local_comparison_controls_exist_and_are_local_only():
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    assert 'save current snapshot' in t
    assert 'use saved baseline' in t
    assert 'use pasted baseline' in t
    assert 'local metadata comparison' in t
    for word in ['execute','apply','approve','verify','rollback','retry','continue','dry-run']:
        assert f'>{word}<' not in t
