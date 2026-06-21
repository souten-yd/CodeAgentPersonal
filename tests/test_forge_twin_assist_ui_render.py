from pathlib import Path


def test_twin_assist_ui_contains_controls_results_and_safety_copy():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "Twin Assist Evaluation" in source
    assert "Run Twin Assist Eval" in source
    assert "baseline" in source and "assisted" in source and "lift" in source and "harm" in source
    assert "twin_localized_slot" in source and "twin_deterministic_anchor" in source
    assert "Evaluation does not apply files or change production routing" in source
    assert "recommended_twin_assist_mode" in source
    assert "recommended_twin_injection_level" in source


def test_twin_assist_ui_uses_forge_api_and_escapes_rendered_values():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "api('/twin-assist/cases?pack_id='" in source
    assert "api('/twin-assist/run'" in source
    assert "escapeHtml(item.case_id)" in source
    assert "textContent = JSON.stringify" in source
