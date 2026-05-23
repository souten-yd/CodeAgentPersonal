import json
from pathlib import Path


def test_vue_15b_safety_regression_contract() -> None:
    m = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    assert m["vue_next_default_enabled"] is True
    assert m["vue_next_default_not_execution_enable"] is True
    assert m["vue_next_execution_enabled"] is False
    assert m["runtime_level"] == "level_0_manual_only"
    assert m["runtime_level"] == "level_0_manual_only"
    assert m["vue_next_workflow_state_execution_eligibility_computed_in_vue"] is False
    assert m["vue_next_workflow_state_mutation_capability"] is False

    ui_html = Path("ui.html").read_text(encoding="utf-8")
    assert "/atlas-next" not in ui_html
