from pathlib import Path

from app.atlas.level1_guarded_execution import (
    build_level1_disabled_readiness_result,
    build_level1_gate_source_map,
)

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_96b_pointer_and_gate_id_consistency_contract() -> None:
    for doc in DOCS:
        t = Path(doc).read_text(encoding='utf-8')
        assert ('Completed automation PR: PR-ATLAS-SCALE-97' in t) or ('Completed automation PR: PR-ATLAS-SCALE-98' in t)
        assert 'Current automation track: PR-ATLAS-SCALE-110' in t
        assert 'Next automation track: PR-ATLAS-SCALE-110' in t
        assert 'next work is PR-ATLAS-SCALE-110' in t
        assert 'next work is PR-ATLAS-SCALE-96' not in t
        assert 'Planned UI track: return to PR-ATLAS-SCALE-96 automation track' not in t

    required = set(build_level1_disabled_readiness_result().required_gates)
    mapped = {item['gate_id'] for item in build_level1_gate_source_map()}
    blockers = {item.gate for item in build_level1_disabled_readiness_result().blockers}
    assert required == mapped
    assert blockers == required
