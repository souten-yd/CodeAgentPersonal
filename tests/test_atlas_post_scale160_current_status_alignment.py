import json
from pathlib import Path


def test_current_status_matches_post_scale160_practical_plan_track() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))
    status = Path('docs/atlas_next_current_status.md').read_text(encoding='utf-8')

    assert manifest['current_automation_track'] == 'POST-SCALE-160-FASTUI-SHELL-MVP'
    assert manifest['next_automation_track'] == 'POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT'
    assert manifest['practical_full_automation_complete'] is False
    assert manifest['ui_practical_experience_complete'] is False
    assert manifest['self_improvement_practical_loop_complete'] is False
    assert manifest['draft_pr_experience_complete'] is False
    assert manifest['practical_full_automation_truthfulness_status'] == 'corrective_checkpoint_in_progress'
    assert manifest['stable_runtime_mutation_apply_complete'] is False
    assert manifest['stable_runtime_mutation_enabled'] is False
    assert manifest['direct_merge_enabled'] is False
    assert manifest['remote_git_push_enabled'] is False
    assert manifest['self_apply_enabled'] is False

    assert 'POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN' in status
    assert 'marks practical completion flags incomplete until evidence exists' in status
    assert 'Practical full automation is not complete at backend-milestone-only state' in status
    assert 'Direct merge, remote push, self-apply, pointer switching, execute-all, Vue authority, and recovery execution remain disabled' in status
