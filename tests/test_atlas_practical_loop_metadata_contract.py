from pathlib import Path

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


def test_practical_loop_metadata_is_rendered_by_fastui_shell_and_client() -> None:
    shell = Path('web/atlas-next/src/components/FastUiShellMvp.vue').read_text(encoding='utf-8')
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')

    for term in ['practicalLoop', 'Loop', 'Draft PR', 'verificationState', 'recoveryState', 'draftPrState']:
        assert term in shell

    for term in [
        'AtlasPracticalLoopMetadata',
        'practical_loop_metadata',
        'normalizePracticalLoopMetadata',
        'executionEnabled: false',
        'directMergeEnabled: false',
        'remoteGitPushEnabled: false',
        'selfApplyEnabled: false',
        'vueAuthoritative: false',
    ]:
        assert term in client

    assert 'practicalLoop: {' in app
