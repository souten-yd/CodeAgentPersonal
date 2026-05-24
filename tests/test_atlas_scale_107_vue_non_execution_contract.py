from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()
def test_no_execution_endpoints_or_dynamic_exec():
    for t in ['/execute','/apply','/approve','/rollback','/retry','/continue','/dry-run','eval(','new Function','Function(']:
        assert t not in TEXT
