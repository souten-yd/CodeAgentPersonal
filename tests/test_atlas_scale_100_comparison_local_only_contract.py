from pathlib import Path

def test_comparison_is_local_and_no_upload_mutation():
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    assert 'json.parse' in t
    assert 'fetchlevel1readinessdiagnostics' in t
    assert 'not a readiness decision' in t
    assert 'not execution eligibility' in t
    assert '/api/atlas/level1/readiness' not in t
