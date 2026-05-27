import json
from pathlib import Path

from app.atlas.practical_loop_metadata import build_latest_practical_loop_workflow_metadata
from app.atlas.workflow_state_contract import build_read_only_workflow_state, summarize_workflow_state_contract


def test_read_only_workflow_state_exposes_practical_loop_metadata_without_authority() -> None:
    payload = build_read_only_workflow_state(
        goal='Improve Atlas workflow',
        project_path='/workspace/CodeAgentPersonal',
        phase='practical_loop_metadata_preview',
        status='metadata_only',
        primary_cta_label='Start Atlas',
        artifacts={'dry_run': True, 'loop_bound': True, 'transaction': True},
        workflow_metadata={
            'practical_loop_status': 'metadata_only',
            'bounded_loop': True,
            'max_iterations': 3,
            'current_iteration': 1,
            'stop_condition': 'manual_review_or_backend_gate',
            'patch_candidate_count': 2,
            'verification_state': 'dry_run_metadata_available',
            'recovery_state': 'not_started',
            'draft_pr_state': 'not_prepared',
        },
    )

    loop = payload['practical_loop_metadata']
    assert loop['schema_version'] == 'atlas.practical_autonomous_dev_loop.v1'
    assert loop['status'] == 'metadata_only'
    assert loop['bounded_loop'] is True
    assert loop['max_iterations'] == 3
    assert loop['current_iteration'] == 1
    assert loop['allowed_actions_enforced'] is True
    assert loop['changed_files_count'] == 2
    assert loop['verification_state'] == 'dry_run_metadata_available'
    assert loop['recovery_state'] == 'not_started'
    assert loop['draft_pr_state'] == 'not_prepared'
    assert loop['execution_enabled'] is False
    assert loop['direct_merge_enabled'] is False
    assert loop['remote_git_push_enabled'] is False
    assert loop['self_apply_enabled'] is False
    assert loop['stable_runtime_mutation_enabled'] is False
    assert loop['vue_authoritative'] is False
    assert loop['advisory_only'] is True

    summary = summarize_workflow_state_contract(payload)
    assert summary['practical_loop_status'] == 'metadata_only'
    assert summary['practical_loop_advisory_only'] is True


def test_latest_practical_loop_artifact_discovery_is_safe_and_read_only(tmp_path: Path) -> None:
    artifact_dir = tmp_path / 'atlas' / 'guarded_operator_loop' / 'pool_1'
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / 'guardloop_abc123.json'
    artifact.write_text(json.dumps({
        'pool_id': 'pool_1',
        'loop_run_id': 'guardloop_abc123',
        'mode': 'advance_to_confirmation',
        'status': 'dry_run_ready',
        'post_refresh_run_id': '',
        'dry_run_result': {'changed_file_count': 3},
        'steps': [{'step': 'queue_built'}, {'step': 'dry_run_completed'}],
        'metadata': {
            'max_iterations': 5,
            'confirmed_action_executed': False,
            'draft_pr_state': 'not_prepared',
        },
        'errors': [],
    }), encoding='utf-8')

    metadata = build_latest_practical_loop_workflow_metadata(data_root=tmp_path)

    assert metadata['practical_loop_status'] == 'dry_run_ready'
    assert metadata['bounded_loop'] is True
    assert metadata['max_iterations'] == 5
    assert metadata['current_iteration'] == 2
    assert metadata['patch_candidate_count'] == 3
    assert metadata['verification_state'] == 'dry_run_metadata_available'
    assert metadata['recovery_state'] == 'not_started'
    assert metadata['draft_pr_state'] == 'not_prepared'
    assert metadata['latest_loop_run_id'] == 'guardloop_abc123'
    assert metadata['latest_loop_pool_id'] == 'pool_1'
    assert metadata['latest_loop_mode'] == 'advance_to_confirmation'
    assert metadata['latest_loop_result_path'] == 'atlas/guarded_operator_loop/pool_1/guardloop_abc123.json'
    assert metadata['latest_loop_action_executed'] is False
    assert metadata['latest_loop_source_detail'] == 'safe_latest_guarded_loop_artifact'


def test_latest_practical_loop_artifact_discovery_empty_state(tmp_path: Path) -> None:
    metadata = build_latest_practical_loop_workflow_metadata(data_root=tmp_path)

    assert metadata['practical_loop_status'] == 'metadata_only'
    assert metadata['bounded_loop'] is False
    assert metadata['latest_loop_run_id'] == ''
    assert metadata['latest_loop_result_path'] == ''
    assert metadata['latest_loop_action_executed'] is False
    assert metadata['latest_loop_source_detail'] == 'no_guarded_loop_artifacts'


def test_practical_loop_metadata_is_rendered_by_fastui_shell_and_client() -> None:
    shell = Path('web/atlas-next/src/components/FastUiShellMvp.vue').read_text(encoding='utf-8')
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')

    for term in [
        'practicalLoop',
        'Loop',
        'Draft PR',
        'verificationState',
        'recoveryState',
        'draftPrState',
        'Loop artifact',
        'loopArtifactDetails',
        'latestLoopPoolId',
        'latestLoopMode',
        'latestLoopResultPath',
        'latestLoopSourceDetail',
        'latestLoopActionExecuted',
        'Action executed',
        'Draft PR artifact',
    ]:
        assert term in shell

    for term in [
        'AtlasPracticalLoopMetadata',
        'practical_loop_metadata',
        'normalizePracticalLoopMetadata',
        'latest_loop_pool_id',
        'latest_loop_mode',
        'latest_loop_result_path',
        'latest_loop_source_detail',
        'latest_loop_action_executed',
        'latestLoopPoolId',
        'latestLoopMode',
        'latestLoopResultPath',
        'latestLoopSourceDetail',
        'latestLoopActionExecuted: item.latest_loop_action_executed === true',
        'executionEnabled: false',
        'directMergeEnabled: false',
        'remoteGitPushEnabled: false',
        'selfApplyEnabled: false',
        'vueAuthoritative: false',
    ]:
        assert term in client

    assert 'practicalLoop: {' in app


def test_practical_loop_discovery_source_has_no_process_network_or_git_dependency() -> None:
    text = Path('app/atlas/practical_loop_metadata.py').read_text(encoding='utf-8')
    forbidden = [
        'subprocess',
        'os.system',
        'requests',
        'from fastapi',
        'import fastapi',
        'git ',
        'safe_apply_to',
        'self_apply_to',
        'merge_pull_request',
    ]
    for needle in forbidden:
        assert needle not in text
