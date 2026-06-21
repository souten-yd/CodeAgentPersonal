"""TA14: runtime policy preview UI block in forge.js."""
from pathlib import Path


def test_runtime_policy_preview_ui_present():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "Runtime Policy Preview" in source
    assert "Preview Runtime Policy" in source
    # Uses the new preview API.
    assert "api('/atlas-generation-policy/preview'" in source
    # Surfaces the auditable fields.
    for field in ("selection mode", "optimal routing enabled", "route fitness applied",
                  "method variant", "twin injection level", "why selected"):
        assert field in source
    # Advisory safety copy.
    assert "does not change production routing" in source


def test_runtime_policy_preview_escapes_values():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "escapeHtml(rtpolicy.selection_mode)" in source
    assert "escapeHtml(rtpolicy.fallback_recommendation.route)" in source
