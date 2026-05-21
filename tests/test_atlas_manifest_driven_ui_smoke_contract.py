import json
from pathlib import Path


MANIFEST_PATH = Path("web/atlas_ui_surface_manifest.json")
HTML_PATH = Path("ui.html")


def _load_manifest():
    assert MANIFEST_PATH.exists(), "manifest missing"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_top_level_metadata_and_vue_checkpoint_fields():
    m = _load_manifest()
    assert m["version"] == 1
    assert m["default_mode"] == "minimal"
    assert m["final_goal"] == "fully_autonomous_code_agent"
    assert m["thinui_role"] == "frontend_simplification_for_autonomous_agent"
    assert m["automation_first"] is True
    assert m["cli_compatible_target"] is True
    assert m["replaceable_ui_target"] is True
    assert m["workflow_state_owner"] == "backend"
    assert m["workflow_state_machine_ui"] is True
    assert m["primary_cta_policy"] == "single_existing_manual_action_only"
    assert m["primary_cta_guard_alignment"] == "operator_loop_guards"

    for key in [
        "vue_migration_checkpoint",
        "vue_target",
        "vue_entry_strategy",
        "legacy_ui_policy",
        "ui_cleanup_policy_doc",
        "vue_migration_plan_doc",
    ]:
        assert key in m and m[key]


def test_manifest_surfaces_are_well_formed_and_dom_mapped_or_allowlisted():
    m = _load_manifest()
    html = HTML_PATH.read_text(encoding="utf-8")
    allowed_categories = {
        "minimal_workflow",
        "advanced_execution",
        "diagnostics",
        "safety_always_visible",
        "deprecated_hidden",
        "future_vue_surface",
        "deprecated",
        "removed_after_migration",
    }

    manifest_only_allowlist = set(m.get("manifest_only_surfaces", []))

    assert isinstance(m["surfaces"], list) and m["surfaces"]
    for surface in m["surfaces"]:
        for key in ["id", "label", "category", "default_visible", "can_hide", "reason", "safety_notes"]:
            assert key in surface
        sid = surface["id"]
        assert sid
        assert surface["category"] in allowed_categories
        in_dom = f'id="{sid}"' in html
        assert in_dom or sid in manifest_only_allowlist
