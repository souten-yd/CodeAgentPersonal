from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_filtering_controls_exist_local_only():
    for token in ['Show all diff gates','Status changes','Evidence changes','Blocker reason changes','Added gates','Removed gates','Summary by source','Summary by before_status','Summary by after_status','Summary by change type','Local display-only diff filter']:
        assert token in TEXT

def test_filter_labels_avoid_execution_words():
    for token in ['execute','apply','approve','verify','rollback','retry','continue','dry-run']:
        assert token not in '\n'.join([line.lower() for line in TEXT.splitlines() if 'option value=' in line or 'Summary by' in line])
