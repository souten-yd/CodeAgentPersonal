import json
from pathlib import Path


def test_vue_15b_manifest_truthfulness_contract() -> None:
    m = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    assert m["vue_next_workflow_state_real_data_connection_status"] in {
        "schema_ready_safe_if_available",
        "safe_read_only_connected",
    }
    if m["vue_next_workflow_state_real_data_connection_status"] == "schema_ready_safe_if_available":
        assert m["vue_next_workflow_state_real_data_source"] == "not_yet_connected"
        assert m["vue_next_workflow_state_unknown_fallback"] is True
        assert m["vue_next_workflow_state_schema_ready"] is True
        assert m["vue_next_workflow_state_real_data_strengthened"] is False
    assert m["runtime_level"] == "level_0_manual_only"
