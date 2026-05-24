from pathlib import Path


def test_label_ui_controls_present():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert 'local diff labels' in text
    assert 'Clear local labels' in text
    assert 'Needs review' in text
    assert 'Ignore locally' in text
