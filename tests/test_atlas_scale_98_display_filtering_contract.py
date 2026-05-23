from pathlib import Path


def test_scale_98_display_filters_are_local_and_non_execution() -> None:
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    for token in ['Display filter:', 'Show all gates', 'Missing evidence only', 'Backend-owned only', 'Frontend-owned only', 'activeFilter']:
        assert token in t
    for banned in ['approve', 'execute', 'apply', 'verify', 'rollback', 'retry', 'continue']:
        assert banned not in t.lower()
