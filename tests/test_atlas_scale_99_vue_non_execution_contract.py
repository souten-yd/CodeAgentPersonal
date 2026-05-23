from pathlib import Path


def test_vue_has_no_execution_endpoints_or_eligibility_logic():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    assert 'compute execution eligibility' in text
    assert 'does not decide readiness' in text
    for endpoint in ['/execute', '/dry-run', '/approve', '/apply', '/rollback', '/retry', '/continue']:
        assert endpoint not in text
