import json
from pathlib import Path


def test_practical_full_automation_manifest_contract() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))

    assert manifest['practical_full_automation_plan'] == 'docs/atlas_practical_full_automation_experience_plan.md'
    assert manifest['practical_full_automation_complete'] is False
    assert manifest['ui_practical_experience_complete'] is False
    assert manifest['stable_runtime_mutation_apply_complete'] is False
    assert manifest['self_improvement_practical_loop_complete'] is False
    assert manifest['draft_pr_experience_complete'] is False

    planned_prs = [item['pr'] for item in manifest['planned_prs']]
    for required in [
        'POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN',
        'POST-SCALE-160-FASTUI-SHELL-MVP',
        'POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP',
        'POST-SCALE-160-SELF-IMPROVEMENT-PRACTICAL-LOOP',
        'POST-SCALE-160-DRAFT-PR-EXPERIENCE',
        'POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT',
    ]:
        assert required in planned_prs

    assert manifest['backend_workflow_state_authoritative'] is True
    assert manifest['self_modification_enabled'] is False
    assert manifest['stable_runtime_mutation_enabled'] is False
    assert manifest['self_apply_enabled'] is False
    assert manifest['remote_git_push_enabled'] is False
    assert manifest['direct_merge_enabled'] is False

    plan_doc = Path(manifest['practical_full_automation_plan']).read_text(encoding='utf-8')
    assert 'POST-SCALE-160-FASTUI-SHELL-MVP' in plan_doc
