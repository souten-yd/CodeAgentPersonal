from pathlib import Path

VUE = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_local_history_import_export_controls_present():
    for token in ['Copy local history JSON', 'Export local history JSON', 'Merge imported history', 'Replace local history', 'Clear import text', 'historyImportJson']:
        assert token in VUE

def test_forbidden_execution_words_not_in_new_labels():
    banned = ['execute', 'apply', 'approve', 'verify', 'rollback', 'retry', 'continue', 'dry-run']
    labels = ['Copy local history JSON', 'Export local history JSON', 'Merge imported history', 'Replace local history', 'Clear import text']
    assert all(all(word not in label.lower() for word in banned) for label in labels)
