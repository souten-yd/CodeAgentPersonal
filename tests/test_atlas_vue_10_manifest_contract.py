import json
from pathlib import Path


def test_vue_10_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_guarded_preview_route'] is True
    assert m['vue_next_preview_route_dist_backed'] is True
    assert m['vue_next_preview_route_fail_closed'] is True
    assert m['vue_next_preview_route_serves_raw_source'] is False
    assert m['vue_next_preview_route_default'] is False
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_mutation_endpoints_enabled'] is False
    assert m['vue_next_action_buttons_enabled'] is False
    assert m['vue_next_backend_authoritative'] is True
    assert m['vue_next_source_of_truth'] is False
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
