import json
from pathlib import Path


def test_vue_default_apply_manifest_matches_guarded_root_route() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))
    main_text = Path('main.py').read_text(encoding='utf-8')

    assert manifest['completed_automation_pr'] == 'POST-SCALE-160-VUE-DEFAULT-PROMOTION-APPLY'
    assert manifest['current_automation_track'] == 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-GATE'
    assert manifest['vue_default_promotion_enabled'] is True
    assert manifest['vue_default_promotion_applied'] is True
    assert manifest['vue_default_promotion_apply_required'] is False
    assert manifest['vue_default_route'] == '/'
    assert manifest['vue_default_legacy_route'] == '/ui/'
    assert manifest['vue_default_requires_valid_dist'] is True
    assert manifest['vue_default_fail_closed_to_legacy_ui'] is True

    assert 'ATLAS_NEXT_DEFAULT_ENABLED = True' in main_text
    assert 'def can_serve_atlas_next_default()' in main_text
    assert 'validation = validate_atlas_next_dist()' in main_text
    assert 'return serve_existing_ui_index()' in main_text
    assert 'RedirectResponse("/atlas-next")' not in main_text


def test_vue_default_apply_does_not_expand_execution_authority() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))
    main_text = Path('main.py').read_text(encoding='utf-8')
    client_text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')

    assert manifest['vue_source_of_truth'] is False
    assert manifest['vue_execution_capability'] == 'none'
    assert manifest['self_modification_enabled'] is False
    assert manifest['direct_merge_enabled'] is False
    assert manifest['stable_runtime_mutation_enabled'] is False

    forbidden_client_tokens = [
        '/execute',
        '/apply',
        '/approve',
        '/rollback',
        '/restore',
        '/verify',
        '/retry',
        '/continue',
    ]
    for token in forbidden_client_tokens:
        assert token not in client_text

    assert 'web/atlas-next/src' not in main_text
    assert 'npm run' not in main_text
