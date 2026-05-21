from pathlib import Path


DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md',
    'docs/atlas_autopilot_scale_master_plan.md',
    'docs/atlas_thinui_readiness.md',
]


def test_scale_79_docs_contract() -> None:
    text = '\n'.join(Path(p).read_text(encoding='utf-8') for p in DOCS)
    for s in [
        'PR-ATLAS-SCALE-79',
        'Current implementation PR:\n- PR-ATLAS-SCALE-81',
        'Next implementation PR:\n- PR-ATLAS-SCALE-82',
        'autonomous execution readiness policy',
        'Level 0 manual-only',
        'Autonomous execution remains forbidden until readiness gates pass',
        'PR-79 does not enable auto-execution',
        'PR-79 does not change runtime behavior',
        'EXECUTE ONE ACTION remains required',
        'Dry-run-first remains required',
        'Suggested commands are not executed automatically',
        'PR-80 remains an out-of-order architecture checkpoint and does not imply PR-79 was previously complete',
        'fully autonomous code agent',
        'Self-improving CodeAgentPersonal / KasaneCore',
    ]:
        assert s in text

    assert 'Current next PR' not in text
