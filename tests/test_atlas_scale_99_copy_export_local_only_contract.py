from pathlib import Path


def test_copy_export_uses_local_diagnostics_and_no_upload_mutation():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert 'JSON.stringify(diagnostics.value' in text
    assert 'navigator.clipboard.writeText' in text
    assert 'createObjectURL' in text
    forbidden = ['fetch(', 'XMLHttpRequest', 'POST', 'PUT', 'PATCH', 'DELETE']
    local_slice = text.split('onMounted(async () =>')[0]
    for token in forbidden:
        assert token not in local_slice
