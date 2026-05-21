from pathlib import Path

DOCS = [
    Path('docs/atlas_development_handoff.md'),
    Path('docs/atlas_scale_master_roadmap.md'),
    Path('docs/atlas_thinui_readiness.md'),
    Path('docs/atlas_unified_autopilot_checkpoint.md'),
    Path('docs/atlas_autopilot_current_status.md'),
    Path('docs/atlas_autopilot_scale_master_plan.md'),
]

def test_scale_75_docs_contract():
    text = '\n'.join(p.read_text(encoding='utf-8') for p in DOCS)
    for s in [
        'Current PR:\n- PR-ATLAS-SCALE-75',
        'Next PR:\n- PR-ATLAS-SCALE-76: Diagnostics drawer and raw JSON isolation',
        'Hide advanced execution panels by default',
        'hidden by default, not removed',
        'diagnostics remain accessible',
        'Backend workflow state is authoritative',
        'replaceable UI',
        'fully autonomous code agent',
        'self-improving CodeAgentPersonal / KasaneCore',
        'Execution semantics remain unchanged',
        'EXECUTE ONE ACTION remains required',
        'Dry-run-first remains required',
    ]:
        assert s in text
    assert 'Current next PR' not in text
