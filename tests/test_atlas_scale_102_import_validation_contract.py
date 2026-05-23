from pathlib import Path
VUE = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_import_uses_json_parse_and_validation():
    assert 'parseHistoryImportPayload' in VUE
    assert 'JSON.parse(raw)' in VUE
    assert 'isValidHistoryEntry' in VUE
    assert 'HISTORY_MAX_ENTRIES' in VUE

def test_no_dynamic_code_execution():
    assert 'eval(' not in VUE
    assert 'new Function' not in VUE
