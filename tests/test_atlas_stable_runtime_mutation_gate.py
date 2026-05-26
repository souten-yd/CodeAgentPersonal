import json
from pathlib import Path

import pytest

from app.atlas.fully_autonomous_code_agent_milestone import validate_fully_autonomous_code_agent_milestone
from app.atlas.stable_runtime_mutation_gate import (
    REQUIRED_CONFIRMATION_TEXT,
    create_stable_runtime_mutation_gate,
    validate_stable_runtime_mutation_gate,
)


def _milestone(data_root: Path, *, status: str = 'ready') -> Path:
    payload = {
        'schema_version': 'atlas.fully_autonomous_code_agent_milestone.v1',
        'milestone_id': 'milestone_1',
        'created_at': '2026-05-26T00:00:00+00:00',
        'track_pr': 'PR-ATLAS-SCALE-160',
        'next_required_pr': 'POST-SCALE-160-CONTINUOUS-IMPROVEMENT',
        'status': status,
        'blocking_reasons': [] if status == 'ready' else ['blocked_for_test'],
        'previous_runtime_level': 'level_7_self_improvement_autonomous_candidate_loop',
        'runtime_level': 'level_8_fully_autonomous_code_agent' if status == 'ready' else 'level_7_self_improvement_autonomous_candidate_loop',
        'target_runtime_level': 'level_8_fully_autonomous_code_agent',
        'runtime_transition_authorized': status == 'ready',
        'backend_authoritative': True,
        'reviewer': 'atlas',
        'autonomous_candidate_loop_path': str(data_root / 'atlas' / 'loop' / 'manifest.json'),
        'autonomous_candidate_loop_schema_version': 'atlas.self_improvement_autonomous_candidate_loop.v1',
        'autonomous_candidate_loop_track_pr': 'PR-ATLAS-SCALE-159',
        'autonomous_candidate_loop_next_required_pr': 'PR-ATLAS-SCALE-160',
        'autonomous_candidate_loop_ready': status == 'ready',
        'milestone_evidence_refs': ['atlas/fully-autonomous/milestone.json'] if status == 'ready' else [],
        'rollback_evidence_refs': ['atlas/fully-autonomous/rollback.json'] if status == 'ready' else [],
        'fully_autonomous_code_agent_milestone_enabled': status == 'ready',
        'fully_autonomous_code_agent_ready': status == 'ready',
        'continuous_improvement_loop_ready': status == 'ready',
        'candidate_workspace_only_until_promotion_gate': True,
        'separate_default_ui_promotion_required': True,
        'separate_stable_runtime_mutation_gate_required': True,
        'separate_direct_merge_gate_required': True,
        'human_review_required_for_stable_mutation': True,
        'stable_runtime_mutation_enabled': False,
        'stable_runtime_mutation_performed': False,
        'self_apply_enabled': False,
        'self_apply_performed': False,
        'self_modification_enabled': False,
        'direct_merge_enabled': False,
        'direct_merge_performed': False,
        'remote_git_push_enabled': False,
        'remote_git_push_performed': False,
        'release_pointer_switch_performed': False,
        'pointer_switch_execution_enabled': False,
        'pointer_switched': False,
        'recovery_execution_performed': False,
        'arbitrary_command_execution_enabled': False,
        'execute_all_enabled': False,
        'default_ui_promotion_enabled': False,
        'vue_authoritative': False,
        'vue_execution_controls_enabled': False,
    }
    validate_fully_autonomous_code_agent_milestone(payload)
    path = data_root / 'atlas' / 'fully_autonomous_code_agent_milestones' / 'milestone_1' / 'manifest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return path


def _approved_kwargs() -> dict[str, object]:
    return {
        'strict_gate_approved': True,
        'confirmation_token_present': True,
        'confirmation_text': REQUIRED_CONFIRMATION_TEXT,
        'approval_status': 'approved',
        'explicit_decision': 'approve',
    }


def test_stable_runtime_mutation_gate_ready_without_mutating_runtime(tmp_path: Path) -> None:
    data_root = tmp_path / 'data'
    milestone_path = _milestone(data_root)

    gate = create_stable_runtime_mutation_gate(
        fully_autonomous_milestone_path=milestone_path,
        data_root=data_root,
        candidate_workspace_ref='atlas/candidates/workspace.json',
        stable_runtime_ref='atlas/stable/runtime-snapshot.json',
        rollback_evidence_refs=['atlas/stable/rollback.json'],
        verification_evidence_refs=['atlas/stable/verification.json'],
        recovery_evidence_refs=['atlas/stable/recovery.json'],
        candidate_workspace_verified=True,
        stable_runtime_snapshot_ready=True,
        rollback_plan_ready=True,
        recovery_plan_ready=True,
        release_pointer_plan_ready=True,
        **_approved_kwargs(),
    )

    assert gate['status'] == 'ready'
    assert gate['track_pr'] == 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-GATE'
    assert gate['next_required_pr'] == 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY'
    assert gate['stable_runtime_mutation_gate_enabled'] is True
    assert gate['stable_runtime_mutation_ready'] is True
    assert gate['stable_runtime_mutation_apply_required'] is True
    assert gate['backend_remains_authoritative'] is True
    assert gate['stable_runtime_mutation_enabled'] is False
    assert gate['stable_runtime_mutation_performed'] is False
    assert gate['release_pointer_switch_performed'] is False
    assert gate['pointer_switch_execution_enabled'] is False
    assert gate['direct_merge_enabled'] is False
    assert gate['remote_git_push_enabled'] is False
    assert gate['self_apply_enabled'] is False
    assert gate['self_modification_enabled'] is False


def test_stable_runtime_mutation_gate_requires_ready_fully_autonomous_milestone(tmp_path: Path) -> None:
    data_root = tmp_path / 'data'
    milestone_path = _milestone(data_root, status='blocked')

    gate = create_stable_runtime_mutation_gate(
        fully_autonomous_milestone_path=milestone_path,
        data_root=data_root,
        candidate_workspace_ref='atlas/candidates/workspace.json',
        stable_runtime_ref='atlas/stable/runtime-snapshot.json',
        rollback_evidence_refs=['atlas/stable/rollback.json'],
        verification_evidence_refs=['atlas/stable/verification.json'],
        recovery_evidence_refs=['atlas/stable/recovery.json'],
        candidate_workspace_verified=True,
        stable_runtime_snapshot_ready=True,
        rollback_plan_ready=True,
        recovery_plan_ready=True,
        release_pointer_plan_ready=True,
        **_approved_kwargs(),
    )

    assert gate['status'] == 'blocked'
    assert 'ready_fully_autonomous_milestone_required' in gate['blocking_reasons']
    assert 'fully_autonomous_ready_required' in gate['blocking_reasons']
    assert gate['stable_runtime_mutation_ready'] is False


def test_stable_runtime_mutation_gate_requires_evidence_and_exact_confirmation(tmp_path: Path) -> None:
    data_root = tmp_path / 'data'
    milestone_path = _milestone(data_root)

    gate = create_stable_runtime_mutation_gate(
        fully_autonomous_milestone_path=milestone_path,
        data_root=data_root,
        candidate_workspace_ref='../outside.json',
        stable_runtime_ref='',
        rollback_evidence_refs=[],
        verification_evidence_refs=['bad.json'],
        recovery_evidence_refs=['../outside.json'],
        candidate_workspace_verified=False,
        stable_runtime_snapshot_ready=False,
        rollback_plan_ready=False,
        recovery_plan_ready=False,
        release_pointer_plan_ready=False,
        strict_gate_approved=False,
        confirmation_token_present=False,
        confirmation_text='MUTATE',
        approval_status='approved',
        explicit_decision='approve',
    )

    assert gate['status'] == 'blocked'
    assert 'candidate_workspace_ref_must_be_relative' in gate['blocking_reasons']
    assert 'candidate_workspace_ref_required' in gate['blocking_reasons']
    assert 'stable_runtime_ref_empty' in gate['blocking_reasons']
    assert 'stable_runtime_ref_required' in gate['blocking_reasons']
    assert 'rollback_evidence_refs_required' in gate['blocking_reasons']
    assert 'verification_evidence_refs_must_include_directory' in gate['blocking_reasons']
    assert 'verification_evidence_refs_required' in gate['blocking_reasons']
    assert 'recovery_evidence_refs_must_be_relative' in gate['blocking_reasons']
    assert 'recovery_evidence_refs_required' in gate['blocking_reasons']
    assert 'candidate_workspace_verification_required' in gate['blocking_reasons']
    assert 'stable_runtime_snapshot_required' in gate['blocking_reasons']
    assert 'rollback_plan_required' in gate['blocking_reasons']
    assert 'recovery_plan_required' in gate['blocking_reasons']
    assert 'release_pointer_plan_required' in gate['blocking_reasons']
    assert 'strict_gate_approval_required' in gate['blocking_reasons']
    assert 'confirmation_token_required' in gate['blocking_reasons']
    assert 'confirmation_text_mismatch' in gate['blocking_reasons']


def test_validate_stable_runtime_mutation_gate_rejects_authority_escalation(tmp_path: Path) -> None:
    data_root = tmp_path / 'data'
    milestone_path = _milestone(data_root)
    gate = create_stable_runtime_mutation_gate(
        fully_autonomous_milestone_path=milestone_path,
        data_root=data_root,
        candidate_workspace_ref='atlas/candidates/workspace.json',
        stable_runtime_ref='atlas/stable/runtime-snapshot.json',
        rollback_evidence_refs=['atlas/stable/rollback.json'],
        verification_evidence_refs=['atlas/stable/verification.json'],
        recovery_evidence_refs=['atlas/stable/recovery.json'],
        candidate_workspace_verified=True,
        stable_runtime_snapshot_ready=True,
        rollback_plan_ready=True,
        recovery_plan_ready=True,
        release_pointer_plan_ready=True,
        **_approved_kwargs(),
    )
    gate['stable_runtime_mutation_enabled'] = True

    with pytest.raises(ValueError, match='invariant_violation:stable_runtime_mutation_enabled'):
        validate_stable_runtime_mutation_gate(gate)


def test_stable_runtime_mutation_gate_source_has_no_process_or_git_execution_dependency() -> None:
    text = Path('app/atlas/stable_runtime_mutation_gate.py').read_text(encoding='utf-8')
    forbidden = [
        'subprocess',
        'os.system',
        'requests',
        'from fastapi',
        'import fastapi',
        'git ',
        'safe_apply',
        'self_apply_to_stable_runtime',
    ]
    for needle in forbidden:
        assert needle not in text
