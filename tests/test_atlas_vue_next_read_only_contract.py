from pathlib import Path
import json


def test_vue_read_only_wording_and_no_mutation_calls():
    vue_text = '\n'.join(p.read_text().lower() for p in Path('web/atlas-next/src').rglob('*') if p.is_file())
    assert 'read-only' in vue_text
    assert 'level 0 manual-only' in vue_text
    assert 'backend workflow state remains authoritative' in vue_text

    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text().lower()
    for forbidden in [
        'fetch(',
        "method: 'post'",
        'method: "post"',
        '/execute',
        '/apply',
        '/approve',
        '/safe_apply',
        '/rollback',
        '/restore',
    ]:
        assert forbidden not in client

    for forbidden in ['execute-all', 'auto-continue', 'safe_apply(', 'rollback(', 'restore(']:
        assert forbidden not in vue_text


def test_manifest_and_docs_contract():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
    assert m['vue_next_foundation'] is True
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_source_of_truth'] is False
    assert m['vue_next_backend_authoritative'] is True
    docs = (Path('docs/atlas_vue_migration_plan.md').read_text() + Path('docs/atlas_scale_master_roadmap.md').read_text()).lower()
    assert 'pr-atlas-vue-01: add parallel vue/vite atlas next read-only shell' in docs
    assert 'current ui track: pr-atlas-vue-02: safe static serving/mount or read-only workflow_state adapter hardening' in docs
    assert 'pr-atlas-scale-93: level-1 guarded execution design checkpoint' in docs
    assert 'existing ui.html remains default' in docs
    assert 'not default' in docs
    assert 'read-only' in docs
    assert 'backend workflow state remains authoritative' in docs
