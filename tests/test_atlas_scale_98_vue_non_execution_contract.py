from pathlib import Path


def test_scale_98_vue_panel_stays_non_execution() -> None:
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    assert 'execution eligibility' in t
    assert 'does not decide readiness' in t
    for banned in ['/api/atlas/level1/execute', '/dry-run', '/apply', '/approve', '/rollback', '/verify', '/retry', '/continue']:
        assert banned not in t
