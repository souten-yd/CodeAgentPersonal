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
