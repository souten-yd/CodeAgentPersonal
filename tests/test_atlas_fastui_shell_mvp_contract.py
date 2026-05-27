import json
from pathlib import Path


def test_fastui_shell_mvp_is_mounted_and_conversation_first() -> None:
    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')
    shell = Path('web/atlas-next/src/components/FastUiShellMvp.vue').read_text(encoding='utf-8')
    requirement = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8')

    assert "import FastUiShellMvp from './FastUiShellMvp.vue'" in app
    assert '<FastUiShellMvp :snapshot="snapshot" />' in app
    assert app.index('<FastUiShellMvp :snapshot="snapshot" />') < app.index('<RequirementInput />')

    required_shell_terms = [
        'FastUI Shell MVP',
        'Conversation first Atlas shell',
        'Work target',
        'software_development_or_repair',
        'platform_self_improvement',
        'Changed files',
        'Verification',
        'Recovery',
        'Start Atlas',
        'Settings',
        'backend workflow state remains authoritative',
        'Vue execution disabled',
    ]
    for term in required_shell_terms:
        assert term in shell

    assert 'id="start-atlas-form"' in requirement
    assert 'Execution controls are intentionally unavailable in Atlas Next.' in requirement


def test_fastui_shell_mvp_preserves_backend_authority_and_forbidden_runtime_actions() -> None:
    shell = Path('web/atlas-next/src/components/FastUiShellMvp.vue').read_text(encoding='utf-8')
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))

    forbidden_shell_terms = [
        'subprocess',
        'os.system',
        'safeApplyEnabled: true',
        'applyEnabled: true',
        'executionEnabled: true',
        'vueAuthoritative: true',
        'remoteGitPushEnabled',
        'directMergeEnabled',
        'selfApplyEnabled',
    ]
    for term in forbidden_shell_terms:
        assert term not in shell

    assert 'vueExecutionEnabled: false' in client
    assert 'backendWorkflowStateAuthoritative: true' in client
    assert manifest['backend_workflow_state_authoritative'] is True
    assert manifest['vue_source_of_truth'] is False
    assert manifest['direct_merge_enabled'] is False
    assert manifest['remote_git_push_enabled'] is False
    assert manifest['self_apply_enabled'] is False
    assert manifest['stable_runtime_mutation_enabled'] is False
