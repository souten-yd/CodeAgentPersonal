import json
from pathlib import Path


def test_ui_default_reconfirmation_records_active_and_future_policies() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))
    notes = Path('docs/atlas_fastui_ux_notes.md').read_text(encoding='utf-8')
    record = Path('docs/atlas_ui_default_reconfirmation.md').read_text(encoding='utf-8')

    assert manifest['completed_automation_pr'] == 'POST-SCALE-160-UI-DEFAULT-RECONFIRM'
    assert manifest['completed_phase'] == 'ui_default_reconfirmation'
    assert manifest['current_automation_track'] == 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY'
    assert manifest['ui_default_reconfirmation_required'] is False
    assert manifest['ui_default_reconfirmed'] is True
    assert manifest['ui_default_reconfirmation_decision'] == 'keep_guarded_atlas_next_default_for_now'
    assert manifest['ui_default_reconfirmation_record'] == 'docs/atlas_ui_default_reconfirmation.md'
    assert manifest['active_ui_default_policy'] == 'guarded_atlas_next_default_with_valid_dist_and_fallback'
    assert manifest['preferred_ui_default_policy'] == 'buildless_thinux_fastui_conversational_shell'
    assert manifest['future_fastui_default_gate_required'] is True

    assert 'Buildless ThinUX / FastUI conversational shell as the normal Atlas experience.' in notes
    assert 'Keep the current guarded Atlas Next root default for now.' in record
    assert 'separate default-route PR' in record


def test_ui_default_reconfirmation_keeps_route_and_authority_guards() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))
    main_text = Path('main.py').read_text(encoding='utf-8')

    assert 'ATLAS_NEXT_DEFAULT_ENABLED = True' in main_text
    assert 'def can_serve_atlas_next_default()' in main_text
    assert 'validate_atlas_next_dist()' in main_text
    assert 'return serve_existing_ui_index()' in main_text
    assert 'RedirectResponse("/atlas-next")' not in main_text
    assert 'web/atlas-next/src' not in main_text
    assert 'npm run' not in main_text

    assert manifest['vue_source_of_truth'] is False
    assert manifest['vue_execution_capability'] == 'none'
    assert manifest['stable_runtime_mutation_enabled'] is False
    assert manifest['direct_merge_enabled'] is False
    assert manifest['remote_git_push_enabled'] is False
    assert manifest['self_apply_enabled'] is False
    assert manifest['self_modification_enabled'] is False
