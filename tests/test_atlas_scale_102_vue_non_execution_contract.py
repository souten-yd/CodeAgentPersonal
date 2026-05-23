from pathlib import Path
VUE=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_no_execution_endpoints_in_vue_panel():
    banned=['/execute','/dry-run','/approve','/apply','/verify','/rollback','/retry','/continue']
    assert all(b not in VUE for b in banned)
