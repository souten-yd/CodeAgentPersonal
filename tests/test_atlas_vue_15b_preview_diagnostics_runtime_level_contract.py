from app.server import get_atlas_next_preview_diagnostics


def test_vue_15b_preview_diagnostics_runtime_level_contract() -> None:
    payload = get_atlas_next_preview_diagnostics()
    assert payload["runtime_level"] == "level_0_manual_only"
    assert payload["read_only"] is True
    assert payload["execution_enabled"] is False
