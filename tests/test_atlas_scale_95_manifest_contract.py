import json
from pathlib import Path


def test_scale_95_manifest_readiness_diagnostics_fields_present() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    expected = {
        'level1_readiness_diagnostics_checkpoint': 'PR-ATLAS-SCALE-95',
        'level1_readiness_diagnostics_enabled': True,
        'level1_readiness_diagnostics_method': 'GET',
        'level1_readiness_diagnostics_metadata_only': True,
        'level1_readiness_diagnostics_execution_enabled': False,
        'level1_readiness_diagnostics_mutation_enabled': False,
        'level1_readiness_diagnostics_endpoint': '/api/atlas/level1/readiness',
        'level1_readiness_diagnostics_reports_disabled_skeleton': True,
        'level1_readiness_diagnostics_reports_blockers': True,
        'runtime_level': 'level_0_manual_only',
        'autonomous_execution_enabled': False,
        'level1_execution_enabled': False,
        'level1_backend_skeleton_execution_enabled': False,
        'level1_callable_execution_endpoint_enabled': False,
    }
    for key, value in expected.items():
        assert manifest.get(key) == value
