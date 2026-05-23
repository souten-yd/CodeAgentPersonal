from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_development_handoff.md',
]

def test_vue21_docs_completion_markers() -> None:
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21' in text
        assert 'Current automation track: PR-ATLAS-SCALE-93' in text
        assert 'VUE21 is not execution-enable' in text
        assert 'VUE21 is next: guarded default enable' not in text
        assert 'Vue remains parallel/read-only/not default' not in text
