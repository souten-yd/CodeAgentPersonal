from pathlib import Path

DOCS=[
 'docs/atlas_development_handoff.md',
 'docs/atlas_unified_autopilot_checkpoint.md',
 'docs/atlas_autopilot_current_status.md',
 'docs/atlas_autopilot_scale_master_plan.md',
 'docs/atlas_scale_master_roadmap.md',
]

def test_active_pointer_and_stale_pointer_cleanup():
    for f in DOCS:
        t=Path(f).read_text(encoding='utf-8')
        assert 'Completed:\n- PR-ATLAS-SCALE-71' in t
        assert 'Current PR:\n- PR-ATLAS-SCALE-71' in t
        assert 'Next PR:\n- PR-ATLAS-SCALE-72: Operator Loop verification recommendation approval copy/export and final contract cleanup' in t
        assert 'Current completed PR: PR-ATLAS-SCALE-68' not in t
        assert 'Next implementation PR: PR-ATLAS-SCALE-70' not in t
        assert 'Current PR: PR-ATLAS-SCALE-70' not in t
        assert 'Next PR: PR-ATLAS-SCALE-71' not in t

def test_docs_capture_manual_approval_and_confirmation_contract():
    t=Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8')
    assert 'manual approval summary' in t
    assert 'advisory-only' in t or 'advisory only' in t
    assert 'EXECUTE ONE ACTION' in t
