from pathlib import Path
import json

def test_manifest_vue17_flags_present_and_safety_preserved() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_plan_review_checkpoint'] == 'PR-ATLAS-VUE-17'
    assert m['vue_next_plan_review_enabled'] is True
    assert m['vue_next_clarification_answer_submission_enabled'] is False
    assert m['vue_next_plan_review_scope'] == 'read_only_review_metadata'
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_mutation_endpoints_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['vue_next_start_atlas_scope'] == 'planning_metadata_only'
