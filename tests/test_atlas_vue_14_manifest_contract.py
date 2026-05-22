import json
from pathlib import Path


def test_vue_14_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_diagnostics_alignment_checkpoint'] == 'PR-ATLAS-VUE-14'
    assert m['vue_next_client_diagnostics_route_mounted'] is True
    assert m['vue_next_client_diagnostics_static_mount_deferred'] is False
    assert m['vue_next_client_diagnostics_route_path'] == '/atlas-next'
    assert m['vue_next_client_diagnostics_route_default'] is False
    assert m['vue_next_client_diagnostics_guarded_route'] is True
    assert m['vue_next_client_diagnostics_dist_backed'] is True
    assert m['vue_next_client_diagnostics_fail_closed'] is True
    assert m['vue_next_backend_diagnostics_route_state_aligned'] is True
    assert m['vue_next_docs_diagnostics_route_state_aligned'] is True
    assert m['vue_next_route_packaging_checkpoint'] == 'PR-ATLAS-VUE-13'
    assert m['vue_next_runtime_build_allowed'] is False
    assert m['vue_next_server_startup_build_allowed'] is False
