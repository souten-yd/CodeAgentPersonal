from pathlib import Path


def test_label_filter_local_only_state_and_export_fields():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert "const activeDiffLabelFilter = ref<DiffLabelFilter>('all')" in text
    assert 'visibleDiffItemsForLabelFilter' in text
    assert 'labelFilterSummaryText' in text
    assert 'local_diff_label_filter' in text
    assert 'local_diff_label_filter_local_only: true' in text
    assert 'label_filter_local_only=' in text
    assert 'label_filter_summary=' in text
