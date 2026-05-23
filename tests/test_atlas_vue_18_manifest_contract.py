from pathlib import Path
import json

def test_manifest_contains_vue18_preview_flags_and_preserves_safety() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_approval_dry_run_preview_checkpoint'] == 'PR-ATLAS-VUE-18'
    assert m['vue_next_approval_preview_enabled'] is True
    assert m['vue_next_dry_run_preview_enabled'] is True
    assert m['vue_next_approval_decision_enabled'] is False
    assert m['vue_next_dry_run_start_enabled'] is False
    assert m['vue_next_execution_start_enabled'] is False
    assert m['vue_next_plan_review_scope'] == 'read_only_review_metadata'
    assert m['vue_next_default_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
