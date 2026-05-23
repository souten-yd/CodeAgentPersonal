from pathlib import Path
import json

def test_manifest_contains_vue19_flags_and_preserves_previous_safety() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_execution_safety_boundary_checkpoint'] == 'PR-ATLAS-VUE-19'
    assert m['vue_next_execution_safety_boundary_enabled'] is True
    assert m['vue_next_execution_boundary_display_only'] is True
    assert m['vue_next_execution_actions_enabled'] is False
    assert m['vue_next_vue21_default_enable_not_execution_enable'] is True
    assert m['vue_next_approval_dry_run_preview_checkpoint'] == 'PR-ATLAS-VUE-18'
    assert m['vue_next_default_enabled'] is True
    assert m['vue_next_default_not_execution_enable'] is True
    assert m['vue_next_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['runtime_level'] == 'level_0_manual_only'
