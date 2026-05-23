from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_diff_annotation_controls_exist_local_only():
    for token in ['Copy diff JSON','Export diff JSON','Copy filtered diff summary','Export filtered diff summary','Save local annotation','Clear local annotation','diffAnnotationStatus']:
        assert token in TEXT

def test_diff_annotation_labels_avoid_execution_words():
    blocked=['execute','apply','approve','verify','rollback','retry','continue','dry-run']
    action_lines='\n'.join([line.lower() for line in TEXT.splitlines() if 'copy diff' in line.lower() or 'export diff' in line.lower() or 'filtered diff summary' in line.lower() or 'local annotation' in line.lower()])
    for token in blocked:
        assert token not in action_lines
