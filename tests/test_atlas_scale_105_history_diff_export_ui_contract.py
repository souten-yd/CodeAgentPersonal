from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_diff_export_controls_exist_local_only():
    for token in ['Copy diff JSON','Export diff JSON','Copy filtered diff summary','Export filtered diff summary','diffExportStatus']:
        assert token in TEXT

def test_diff_export_labels_avoid_execution_words():
    blocked=['execute','apply','approve','verify','rollback','retry','continue','dry-run']
    action_lines='\n'.join([line.lower() for line in TEXT.splitlines() if 'Copy diff' in line or 'Export diff' in line or 'filtered diff summary' in line])
    for token in blocked:
        assert token not in action_lines
