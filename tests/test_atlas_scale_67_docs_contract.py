from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
    'docs/atlas_scale_master_roadmap.md',
]

def _active_section(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    keys = ('Current completed PR', 'Current PR', 'Next PR', 'Current next PR', 'Next implementation PR')
    return '\n'.join([ln for ln in lines if any(k in ln for k in keys)])


def test_docs_active_pointers_and_advisory_contract():
    docs = {p: Path(p).read_text() for p in DOCS}
    full = '\n'.join(docs.values())
    active = '\n'.join(_active_section(v) for v in docs.values())
    assert 'PR-ATLAS-SCALE-67B' in full
    assert 'PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2' in full
    assert 'Planner Packaging v2' in full and 'advisory-only' in full
    assert 'Context Refresh v2' in full and 'PlanItem Impact Map' in full
    assert 'Current completed PR: PR-ATLAS-SCALE-66C' not in active
    assert 'Next implementation PR: PR-ATLAS-SCALE-67' not in active
    assert 'Current next PR: PR-ATLAS-SCALE-67' not in active
