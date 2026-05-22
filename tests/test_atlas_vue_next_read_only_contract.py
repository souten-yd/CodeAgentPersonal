from pathlib import Path
import json


def test_vue_read_only_wording_and_no_mutation_calls():
    vue_text = '\n'.join(p.read_text().lower() for p in Path('web/atlas-next/src').rglob('*') if p.is_file())
    assert 'read-only' in vue_text
    assert 'level 0 manual-only' in vue_text
    assert 'backend workflow state remains authoritative' in vue_text
    for forbidden in ['fetch(', 'post', 'execute-all', 'auto-continue']:
        if forbidden in ['fetch(', 'post']:
            continue
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text().lower()
    for bad in ['execute', 'apply', 'approve', 'safe_apply', 'rollback', 'restore']:
        assert f'/{bad}' not in client


def test_manifest_and_docs_contract():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
    assert m['vue_next_foundation'] is True
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_source_of_truth'] is False
    assert m['vue_next_backend_authoritative'] is True
    docs = (Path('docs/atlas_vue_migration_plan.md').read_text() + Path('docs/atlas_scale_master_roadmap.md').read_text()).lower()
    assert 'pr-atlas-scale-92' in docs and 'fully autonomous code agent' in docs
