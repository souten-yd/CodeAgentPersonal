from pathlib import Path

def test_client_endpoint_set_remains_safe() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert '/api/atlas/workflow-state/read-only' in text
    assert '/api/atlas/plan-pools' in text
    for banned in ['/approvals/decide','/dry-run','/execute','/apply','/verify','/rollback','/restore','/retry','/continue']:
        assert banned not in text
