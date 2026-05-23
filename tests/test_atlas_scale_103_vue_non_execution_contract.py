from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_no_level1_execution_endpoints_or_dynamic_execution():
    banned=['/execute','/apply','/approve','/verify','/rollback','/retry','/continue','new Function','eval(']
    for token in banned:
        assert token not in TEXT
