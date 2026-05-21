import json
from pathlib import Path

def test_rollup_manifest_contract():
    m=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
    assert m['readiness_gate_rollup_foundation'] is True
    assert m['readiness_gate_rollup_runtime_gate']=='metadata_only_manual_foundation'
    assert m['level0_readiness_foundation_complete'] is True
    assert m['level0_completion_checkpoint']=='PR-ATLAS-SCALE-92'
    assert m['runtime_level']=='level_0_manual_only'
    assert m['level1_execution_enabled'] is False
    assert m['readiness_rollup_auto_execute_enabled'] is False
    assert m['vue_next_allowed_after_pr92'] is True and m['vue_next_started'] is False and m['vue_next_default_enabled'] is False and m['vue_next_execution_enabled'] is False
    assert m['final_goal']=='fully_autonomous_code_agent' and m['self_improvement_scope']=='self_improving_codeagentpersonal_kasanecore'
