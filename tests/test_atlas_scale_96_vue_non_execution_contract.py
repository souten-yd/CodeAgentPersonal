from pathlib import Path

def test_scale_96_vue_endpoint_set() -> None:
    js=Path('web/js/atlas_pipeline_api.js').read_text()
    ts=Path('web/atlas-next/src/api/atlasClient.ts').read_text()
    assert '/api/atlas/workflow-state/read-only' in ts
    assert '/api/atlas/plan-pools' in ts
    banned=['/dry-run','/execute','/apply','/approve','/rollback','/restore','/verify','/retry','/continue']
    for b in banned:
        assert b not in ts
