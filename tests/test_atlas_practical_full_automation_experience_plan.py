import json
from pathlib import Path


def test_practical_full_automation_plan_manifest_wiring() -> None:
    assert Path('docs/atlas_practical_full_automation_experience_plan.md').exists()

    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))
    assert manifest['practical_full_automation_plan'] == 'docs/atlas_practical_full_automation_experience_plan.md'
    assert manifest['practical_full_automation_complete'] is False
    assert manifest['ui_practical_experience_complete'] is False
    assert manifest['self_improvement_practical_loop_complete'] is False
    assert manifest['draft_pr_experience_complete'] is False

    planned_prs = {item['pr'] for item in manifest['planned_prs']}
    assert 'POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN' in planned_prs
    assert 'POST-SCALE-160-FASTUI-SHELL-MVP' in planned_prs
    assert 'POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP' in planned_prs
    assert 'POST-SCALE-160-SELF-IMPROVEMENT-PRACTICAL-LOOP' in planned_prs
    assert 'POST-SCALE-160-DRAFT-PR-EXPERIENCE' in planned_prs
    assert 'POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT' in planned_prs

    assert manifest['current_automation_track'] == 'POST-SCALE-160-FASTUI-SHELL-MVP'
    assert manifest['next_automation_track'] == 'POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP'
    assert manifest['next_level_advancement_pr'] == 'POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT'
    assert manifest['direct_merge_enabled'] is False
    assert manifest['remote_git_push_enabled'] is False
    assert manifest['self_apply_enabled'] is False
    assert manifest['self_modification_enabled'] is False
    assert manifest['vue_source_of_truth'] is False
