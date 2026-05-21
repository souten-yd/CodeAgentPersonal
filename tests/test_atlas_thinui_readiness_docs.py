from pathlib import Path


def test_thinui_readiness_doc_contract() -> None:
    p = Path('docs/atlas_thinui_readiness.md')
    assert p.exists()
    t = p.read_text(encoding='utf-8')
    for s in [
        'ThinUI',
        'Minimal Workflow UI',
        'Advanced Execution Controls',
        'Diagnostics / Developer Tools',
        'fully autonomous code agent',
        'goal → research → plan → implement → test → fix → PR',
        'self-improving CodeAgentPersonal/KasaneCore',
        'ThinUI does not change the final goal',
        'EXECUTE ONE ACTION remains required',
        'dry-run-first remains required',
        'suggested commands are not executed automatically',
        'Self-Improvement Scope',
        'Self-improvement remains explicitly in scope',
        'Snapshot / restore / patch transaction / rollback',
        'stricter gates than ordinary repo work',
        'ThinUI does not replace self-improvement',
        'PR-91〜PR-100 Self-Improving Atlas / KasaneCore Roadmap',
    ]:
        assert s in t
