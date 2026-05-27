import json
from pathlib import Path

import pytest

from app.atlas.fully_autonomous_code_agent_milestone import validate_fully_autonomous_code_agent_milestone
from app.atlas.stable_runtime_mutation_apply import (
    REQUIRED_CONFIRMATION_TEXT,
    create_stable_runtime_mutation_apply,
    validate_stable_runtime_mutation_apply,
)
from app.atlas.stable_runtime_mutation_gate import create_stable_runtime_mutation_gate


def _milestone(data_root: Path) -> Path:
    payload = {
        'schema_version': 'atlas.fully_autonomous_code_agent_milestone.v1',
        'milestone_id': 'milestone_1',
        'created_at': '2026-05-26T00:00:00+00:00',
        'track_pr': 'PR-ATLAS-SCALE-160',
        'next_required_pr': 'POST-SCALE-160-CONTINUOUS-IMPROVEMENT',
        'status': 'ready',
        'blocking_reasons': [],
        'previous_runtime_level': 'level_7_self_improvement_autonomous_candidate_loop',
        'runtime_level': 'level_8_fully_autonomous_code_agent',
        'target_runtime_level': 'level_8_fully_autonomous_code_agent',
        'runtime_transition_authorized': True,
        'backend_authoritative': True,
        'reviewer': 'atlas',
        'autonomous_candidate_loop_path': str(data_root / 'atlas' / 'loop' / 'manifest.json'),
        'autonomous_candidate_loop_schema_version': 'atlas.self_improvement_autonomous_candidate_loop.v1',
        'autonomous_candidate_loop_track_pr': 'PR-ATLAS-SCALE-159',
        'autonomous_candidate_loop_next_required_pr': 'PR-ATLAS-SCALE-160',
        'autonomous_candidate_loop_ready': True,
        'milestone_evidence_refs': ['atlas/fully-autonomous/milestone.json'],
        'rollback_evidence_refs': ['atlas/fully-autonomous/rollback.json'],
        'fully_autonomous_code_agent_milestone_enabled': True,
        'fully_autonomous_code_agent_ready': True,
        'continuous_improvement_loop_ready': True,
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


def _approved_gate(data_root: Path) -> dict[str, object]:
    return create_stable_runtime_mutation_gate(
        fully_autonomous_milestone_path=_milestone(data_root),
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
        strict_gate_approved=True,
        confirmation_token_present=True,
        confirmation_text='PREPARE STABLE RUNTIME MUTATION GATE',
        approval_status='approved',
        explicit_decision='approve',
    )


def _blocked_gate(data_root: Path) -> dict[str, object]:
    return create_stable_runtime_mutation_gate(
        fully_autonomous_milestone_path=_milestone(data_root),
        data_root=data_root,
        candidate_workspace_ref='atlas/candidates/workspace.json',
        stable_runtime_ref='atlas/stable/runtime-snapshot.json',
        rollback_evidence_refs=[],
        verification_evidence_refs=['atlas/stable/verification.json'],
        recovery_evidence_refs=['atlas/stable/recovery.json'],
        candidate_workspace_verified=True,
        stable_runtime_snapshot_ready=True,
        rollback_plan_ready=False,
        recovery_plan_ready=True,
        release_pointer_plan_ready=True,
        strict_gate_approved=True,
        confirmation_token_present=True,
        confirmation_text='PREPARE STABLE RUNTIME MUTATION GATE',
        approval_status='approved',
        explicit_decision='approve',
    )


def _approved_apply_kwargs() -> dict[str, object]:
    return {
        'strict_gate_approved': True,
        'confirmation_token_present': True,
        'confirmation_text': REQUIRED_CONFIRMATION_TEXT,
        'approval_status': 'approved',
        'explicit_decision': 'approve',
    }


def test_stable_runtime_mutation_apply_records_mutation_without_pointer_or_git_side_effects(tmp_path: Path) -> None:
    apply_record = create_stable_runtime_mutation_apply(
        gate=_approved_gate(tmp_path / 'data'),
        **_approved_apply_kwargs(),
    )

    assert apply_record['status'] == 'applied'
    assert apply_record['track_pr'] == 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY'
    assert apply_record['next_required_pr'] == 'POST-SCALE-160-DIRECT-MERGE-GATE'
    assert apply_record['stable_runtime_mutation_enabled'] is True
    assert apply_record['stable_runtime_mutation_performed'] is True
    assert apply_record['stable_runtime_mutation_apply_required'] is False
    assert apply_record['stable_runtime_mutation_apply_record_only'] is True
    assert apply_record['stable_runtime_ref'] == 'atlas/stable/runtime-snapshot.json'
    assert apply_record['backend_remains_authoritative'] is True
    assert apply_record['release_pointer_switch_performed'] is False
    assert apply_record['pointer_switch_execution_enabled'] is False
    assert apply_record['pointer_switched'] is False
    assert apply_record['direct_merge_enabled'] is False
    assert apply_record['remote_git_push_enabled'] is False
    assert apply_record['self_apply_enabled'] is False
    assert apply_record['self_modification_enabled'] is False
    assert apply_record['vue_execution_controls_enabled'] is False


def test_stable_runtime_mutation_apply_requires_ready_gate_and_exact_confirmation(tmp_path: Path) -> None:
    apply_record = create_stable_runtime_mutation_apply(
        gate=_blocked_gate(tmp_path / 'data'),
        strict_gate_approved=False,
        confirmation_token_present=False,
        confirmation_text='MUTATE',
        approval_status='approved',
        explicit_decision='approve',
    )

    assert apply_record['status'] == 'blocked'
    assert 'ready_stable_runtime_mutation_gate_required' in apply_record['blocking_reasons']
    assert 'stable_runtime_mutation_gate_ready_required' in apply_record['blocking_reasons']
    assert 'strict_gate_approval_required' in apply_record['blocking_reasons']
    assert 'confirmation_token_required' in apply_record['blocking_reasons']
    assert 'confirmation_text_mismatch' in apply_record['blocking_reasons']
    assert apply_record['stable_runtime_mutation_enabled'] is False
    assert apply_record['stable_runtime_mutation_performed'] is False


def test_validate_stable_runtime_mutation_apply_rejects_forbidden_authority_escalation(tmp_path: Path) -> None:
    apply_record = create_stable_runtime_mutation_apply(
        gate=_approved_gate(tmp_path / 'data'),
        **_approved_apply_kwargs(),
    )
    apply_record['direct_merge_enabled'] = True

    with pytest.raises(ValueError, match='invariant_violation:direct_merge_enabled'):
        validate_stable_runtime_mutation_apply(apply_record)


def test_stable_runtime_mutation_apply_source_has_no_process_network_or_git_dependency() -> None:
    text = Path('app/atlas/stable_runtime_mutation_apply.py').read_text(encoding='utf-8')
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
