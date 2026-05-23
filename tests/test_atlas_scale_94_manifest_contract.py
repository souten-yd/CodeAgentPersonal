import json
from pathlib import Path


def test_scale_94_manifest_flags() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['level1_disabled_backend_skeleton_checkpoint'] == 'PR-ATLAS-SCALE-94'
    assert manifest['level1_backend_skeleton_enabled'] is True
    assert manifest['level1_backend_skeleton_execution_enabled'] is False
    assert manifest['level1_callable_execution_endpoint_enabled'] is False
    assert manifest['level1_route_exposed'] is False
    assert manifest['level1_metadata_only'] is True
    assert manifest['runtime_level'] == 'level_0_manual_only'
    assert manifest['level1_execution_enabled'] is False
    assert manifest['autonomous_execution_enabled'] is False
