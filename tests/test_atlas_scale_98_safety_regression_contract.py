from pathlib import Path


def test_scale_98_no_readiness_mutation_methods_in_vue() -> None:
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    assert 'fetchLevel1ReadinessDiagnostics' in t
    for banned in ['method: \"POST\"', "method: 'POST'", 'method: \"PUT\"', "method: 'PUT'", 'method: \"PATCH\"', "method: 'PATCH'", 'method: \"DELETE\"', "method: 'DELETE'"]:
        assert banned not in t
