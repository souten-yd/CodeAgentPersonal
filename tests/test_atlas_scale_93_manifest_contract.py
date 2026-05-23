import json
from pathlib import Path


def test_scale_93_manifest_fields_and_runtime_contract() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    expected = {
        'level1_guarded_execution_design_checkpoint': 'PR-ATLAS-SCALE-93',
        'level1_guarded_execution_design_defined': True,
        'level1_execution_enabled': False,
        'level1_backend_skeleton_enabled': False,
        'level1_vue_execution_controls_enabled': False,
        'level1_requires_dry_run_first': True,
        'level1_requires_explicit_human_approval': True,
        'level1_requires_single_action_only': True,
        'level1_allows_auto_continue': False,
        'level1_allows_execute_all': False,
        'level1_allows_autonomous_loop': False,
        'level1_allows_remote_git_push': False,
        'level1_allows_self_modification_execution': False,
        'level1_required_gates_defined': True,
        'level1_next_pr_may_add_disabled_backend_skeleton': True,
        'runtime_level': 'level_0_manual_only',
        'autonomous_execution_enabled': False,
        'vue_next_default_enabled': True,
        'vue_next_default_not_execution_enable': True,
    }
    for k,v in expected.items():
        assert manifest.get(k)==v
