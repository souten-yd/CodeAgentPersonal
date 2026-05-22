from pathlib import Path


def test_vue_03_workflow_cards_read_only_contract() -> None:
    vue_text = '\n'.join(
        p.read_text(encoding='utf-8').lower()
        for p in Path('web/atlas-next/src').rglob('*')
        if p.is_file()
    )
    docs_text = (
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower()
        + '\n'
        + Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower()
    )
    combined = vue_text + '\n' + docs_text

    for required in [
        'read-only',
        'level 0 manual-only',
        'backend workflow state remains authoritative',
        'existing ui.html remains default',
        'metadata only',
        'dry-run-first',
        'execute one action',
    ]:
        assert required in combined

    for concept in ['snapshot','transaction','risk','allowlist','dry-run','rollback','stop','loop','rollup']:
        assert concept in combined

    assert ('artifact capture' in combined) or ('artifact_capture' in combined)
    assert ('remote git' in combined) or ('remote_git' in combined)
    assert ('self-improvement' in combined) or ('self_improvement' in combined)

    assert 'available actions (metadata only)' in vue_text
    assert 'read-only metadata only. execution remains disabled in vue next.' in vue_text


def test_vue_03_buttons_disabled_and_no_mutation_handlers() -> None:
    component_text = '\n'.join(
        p.read_text(encoding='utf-8').lower()
        for p in Path('web/atlas-next/src/components').rglob('*.vue')
    )

    assert '<button disabled>' in component_text or 'aria-disabled="true"' in component_text

    for forbidden in [
        '/execute',
        '/apply',
        '/approve',
        '/safe_apply',
        '/rollback',
        '/restore',
        '/run',
        '/verify',
        '/retry',
        '/continue',
        'onclick=',
        '@click=',
    ]:
        assert forbidden not in component_text

    api_text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8').lower()
    for forbidden in [
        'fetch(',
        'axios.',
        'xmlhttprequest',
        'method: "post"',
        "method: 'post'",
        'method: "put"',
        "method: 'put'",
        'method: "patch"',
        "method: 'patch'",
        'method: "delete"',
        "method: 'delete'",
    ]:
        assert forbidden not in api_text
