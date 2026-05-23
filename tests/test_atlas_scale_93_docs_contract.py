from pathlib import Path

DOCS = [
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_thinui_readiness.md',
]

GATES = [
    'Snapshot/restore readiness',
    'Patch transaction readiness',
    'Risk classification readiness',
    'Dry-run proof readiness',
    'Explicit approval token readiness',
    'Allowlisted verification readiness',
    'Rollback readiness',
    'Artifact capture readiness',
    'Stop/kill switch readiness',
    'Loop bound readiness',
    'Remote git restriction readiness',
    'Self-improvement gate readiness',
    'Audit log readiness',
    'data_root/path safety readiness',
    'Forbidden command execution policy',
    'Backend authority enforcement',
    'UI non-authority enforcement',
]


def test_scale_93_docs_include_gate_matrix_and_design_only_boundary() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'PR-ATLAS-SCALE-93 Level-1 Guarded Execution Design Checkpoint' in text
        assert 'SCALE-93 is a design-only checkpoint' in text
        assert 'Runtime remains `level_0_manual_only`' in text
        for gate in GATES:
            assert gate in text
