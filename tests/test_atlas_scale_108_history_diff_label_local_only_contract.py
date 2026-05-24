from pathlib import Path


def test_label_state_local_only_and_exported_local_only():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert 'DIFF_LABEL_STORAGE_KEY' in text
    assert 'localStorage' in text
    assert 'local_diff_labels' in text
    assert 'local_diff_labels_local_only: true' in text
