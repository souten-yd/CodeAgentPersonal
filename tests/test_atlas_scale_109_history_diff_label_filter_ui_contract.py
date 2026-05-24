from pathlib import Path


def test_label_filter_controls_present_and_non_execution_language():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert 'Readiness local history diff label filtering controls' in text
    assert 'Show all labels' in text
    assert 'Show unlabeled only' in text
    assert 'Clear label filter' in text
    banned = ['execute', 'apply', 'approve', 'verify', 'rollback', 'retry', 'continue', 'dry-run']
    label_filter_block = text.split('Readiness local history diff label filtering controls', 1)[1].split('Readiness local history diff label actions', 1)[0].lower()
    for token in banned:
        assert token not in label_filter_block
