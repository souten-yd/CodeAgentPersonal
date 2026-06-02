import json
from pathlib import Path


def test_practical_full_automation_manifest_contract() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))

    assert manifest['practical_full_automation_plan'] == 'docs/atlas_practical_full_automation_experience_plan.md'
    assert manifest['practical_full_automation_complete'] is True
    assert manifest['ui_practical_experience_complete'] is True
    assert manifest['stable_runtime_mutation_apply_complete'] is False
    assert manifest['self_improvement_practical_loop_complete'] is True
    assert manifest['draft_pr_experience_complete'] is True
    assert manifest['practical_full_automation_truthfulness_status'] == 'accepted_with_evidence'
    assert manifest['practical_full_automation_incomplete_reasons'] == []
    assert manifest['practical_full_automation_completion_evidence']['acceptance_tests_passed'] is True
    assert manifest['practical_full_automation_acceptance_tests'] == 'tests/test_atlas_practical_full_automation_acceptance.py'
    assert manifest['completed_phase'] == 'practical_full_automation_checkpoint_accepted'

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
    assert manifest['current_automation_track'] == 'POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT'
    assert manifest['next_automation_track'] == 'SUPERVISED-FUTURE-GATE-ONLY'
    assert manifest['next_level_advancement_pr'] == 'POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT'
    assert manifest['self_modification_enabled'] is False
    assert manifest['stable_runtime_mutation_enabled'] is False
    assert manifest['stable_runtime_mutation_apply_record_only'] is True
    assert manifest['stable_runtime_mutation_performed'] is False
    assert manifest['self_apply_enabled'] is False
    assert manifest['remote_git_push_enabled'] is False
    assert manifest['direct_merge_enabled'] is False
    assert manifest['vue_source_of_truth'] is False
    assert manifest['default_conversational_shell_requires_vue'] is False
    assert manifest['default_conversational_shell_requires_vite'] is False

    plan_doc = Path(manifest['practical_full_automation_plan']).read_text(encoding='utf-8')
    assert 'accepted practical Atlas plan' in plan_doc
    assert 'does not enable direct merge' in plan_doc
    policy_doc = Path(manifest['canonical_safety_policy']).read_text(encoding='utf-8')
    assert 'Self-platform work remains candidate-workspace-only' in policy_doc
    assert 'Supervised auto-merge readiness is a report' in policy_doc
    assert 'does not enable unbounded automation' in policy_doc
