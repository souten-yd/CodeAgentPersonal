from pathlib import Path


def test_scale_97_vue_has_no_execution_controls() -> None:
    t=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    for banned in ['/api/atlas/level1/execute','dry-run','approve','apply','verify','rollback','retry','continue']:
        assert banned not in t
