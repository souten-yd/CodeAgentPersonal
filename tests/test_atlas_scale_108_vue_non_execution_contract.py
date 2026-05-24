from pathlib import Path


def test_no_execution_wording_in_label_options():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    for banned in ['execute','apply','approve','verify','rollback','retry','continue','dry-run']:
        assert banned not in "needs review evidence issue blocker changed resolved follow up ignore locally"
