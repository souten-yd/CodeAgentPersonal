from agent.model_forge import (
    BenchmarkPreset,
    get_preset,
    load_presets,
    preset_listing,
    validate_preset,
)


def test_required_task_family_presets_exist() -> None:
    ids = {p.preset_id for p in load_presets()}
    # Acceptance minimum: Quick, Web App, Repair, Greenfield.
    assert {"quick_standard", "web_app_standard", "repair_standard", "greenfield_standard"} <= ids


def test_every_builtin_preset_is_valid() -> None:
    for preset in load_presets():
        assert validate_preset(preset) == []
        assert preset.tasks
        assert preset.required_evaluators
        assert preset.runtime_budget_seconds > 0


def test_validation_flags_missing_fields() -> None:
    bad = BenchmarkPreset(preset_id="x", tasks=[], required_evaluators=[], runtime_budget_seconds=0)
    reasons = validate_preset(bad)
    assert "no_tasks" in reasons
    assert "no_required_evaluators" in reasons
    assert "non_positive_runtime_budget" in reasons


def test_get_preset_returns_known_and_none_for_unknown() -> None:
    assert get_preset("web_app_standard").category == "web_app"
    assert get_preset("does_not_exist") is None


def test_preset_listing_is_api_ready() -> None:
    listing = preset_listing()
    assert listing
    item = next(p for p in listing if p["preset_id"] == "web_app_standard")
    assert item["task_count"] == 2
    assert "portal_preview" in item["required_evaluators"]
    assert "patch_dsl" in item["recommended_routes"]
    assert item["runtime_budget_seconds"] > 0
    assert item["profile_dimensions"]
