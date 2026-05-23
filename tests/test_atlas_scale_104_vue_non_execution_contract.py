from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text().lower()

def test_vue_has_no_execution_controls_or_routes_added():
    for token in ['/api/atlas/level1/execute','/dry-run','safe_apply','subprocess','execute-all','auto-continue']:
        assert token not in TEXT
