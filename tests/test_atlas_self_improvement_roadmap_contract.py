from pathlib import Path


def test_scale_master_self_improvement_contract() -> None:
    t = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8')
    for s in [
        'PR-91〜PR-100 Self-Improving Atlas / KasaneCore Roadmap',
        'PR-91',
        'PR-100',
        'self-improving CodeAgentPersonal/KasaneCore',
        'Self-improvement Safety Boundary',
        'strict-gate',
        'launcher',
        'Docker',
        'runtime',
        'UI',
        'safety',
        'snapshot',
        'restore',
        'patch transaction',
        'rollback',
        'draft PR',
        'no direct merge',
    ]:
        assert s in t


def test_self_development_rules_boundary_contract() -> None:
    t = Path('docs/atlas_self_development_rules.md').read_text(encoding='utf-8')
    for s in [
        'Self-Improvement Roadmap Boundary',
        'strict-gate',
        'snapshot',
        'restore',
        'rollback proof',
        'No direct merge / push / remote git write until an explicit future policy PR',
    ]:
        assert s in t
