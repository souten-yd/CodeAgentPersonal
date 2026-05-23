import json
from pathlib import Path


def test_scale_98_manifest_fields_and_safety_preserved() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
    assert m['level1_readiness_ui_refinement_checkpoint'] == 'PR-ATLAS-SCALE-98'
    assert m['level1_readiness_ui_grouping_enabled'] is True
    assert m['level1_readiness_ui_filtering_display_only'] is True
    assert m['level1_readiness_ui_computes_execution_eligibility'] is False
    assert m['level1_readiness_ui_decides_readiness'] is False
    assert m['level1_readiness_ui_mutation_enabled'] is False
    assert m['level1_readiness_ui_execution_enabled'] is False
    assert m['level1_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
