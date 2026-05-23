from pathlib import Path

def test_readiness_endpoint_get_only_contract_tokens():
    vue = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8').lower()
    assert '/api/atlas/level1/readiness' in vue
    assert 'method: "post"' not in vue
    assert 'method: "put"' not in vue
    assert 'method: "patch"' not in vue
    assert 'method: "delete"' not in vue


def test_execute_all_and_auto_continue_not_enabled_wording():
    text = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8').lower()
    assert 'auto-continue / no execute-all' in text
