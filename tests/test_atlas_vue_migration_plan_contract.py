from pathlib import Path


def test_vue_migration_plan_contract() -> None:
    p = Path('docs/atlas_vue_migration_plan.md')
    assert p.exists()
    t = p.read_text(encoding='utf-8')
    for s in [
        'Vue 3 + Vite + TypeScript',
        'Do not use Nuxt',
        'parallel UI',
        'backend workflow_state',
        'workflow_state',
        'available_actions',
        'fully autonomous code agent',
        'self-improving CodeAgentPersonal / KasaneCore',
        'Existing ui.html remains',
        'legacy',
        'Default Switch Criteria',
        'dry-run-first',
        'EXECUTE ONE ACTION',
        'No execution semantics change',
    ]:
        assert s in t
    assert 'replace the current UI immediately' not in t
    assert 'make Vue the default UI immediately' not in t


def test_pr92_prereq_and_vue01_track_language():
    t = Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8')
    for s in ['PR-ATLAS-SCALE-92','separate UI track','read-only','not default','PR-80 was planning only']:
        assert s in t


def test_vue_migration_plan_v04_checkpoint_language():
    t = Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8')
    for s in ['PR-ATLAS-VUE-04','safe backend GET adapter/static mount decision','PR-ATLAS-VUE-05','PR-ATLAS-SCALE-93','ui.html remains default']:
        assert s in t
