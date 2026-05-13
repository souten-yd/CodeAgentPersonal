from pathlib import Path


def test_format_status_uses_phase_step_marker_contract():
    text = Path('web/js/nexus.js').read_text(encoding='utf-8')
    assert 'phaseIndex' in text
    assert 'phaseTotal' in text
    assert '`${phaseIndex}/${phaseTotal} ${phaseLabel}`' in text
