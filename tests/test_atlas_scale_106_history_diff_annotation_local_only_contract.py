from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_filtering_uses_local_comparison_result_only():
    for token in ['visibleChangedGates','visibleAddedGates','visibleRemovedGates','comparisonResult.value','diffSourceSummaryText','diffChangeTypeSummaryText']:
        assert token in TEXT

def test_filtering_has_no_backend_mutation_calls():
    for token in ['POST','PUT','PATCH','DELETE','/execute','/apply','/approve']:
        assert token not in TEXT
