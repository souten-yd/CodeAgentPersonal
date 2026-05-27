import json
from pathlib import Path


def test_current_status_matches_post_scale160_practical_plan_track() -> None:
    manifest = json.loads(Path('docs/atlas_automation_phase_manifest.json').read_text(encoding='utf-8'))
    status = Path('docs/atlas_next_current_status.md').read_text(encoding='utf-8')

    assert manifest['current_automation_track'] == 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY'
    assert manifest['next_automation_track'] == 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY'
    assert manifest['practical_full_automation_complete'] is False
    assert manifest['stable_runtime_mutation_apply_complete'] is False
    assert manifest['stable_runtime_mutation_enabled'] is False
    assert manifest['direct_merge_enabled'] is False
    assert manifest['remote_git_push_enabled'] is False
    assert manifest['self_apply_enabled'] is False

    assert 'POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN' in status
    assert 'Stable runtime mutation apply remains the active track' in status
    assert 'POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY: complete the stable runtime mutation apply evidence path' in status
    assert 'POST-SCALE-160-DIRECT-MERGE-GATE: prepare direct merge policy' not in status
