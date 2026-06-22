"""UI consolidation: the Twin Assist sub-tab was removed; its evaluation runs inline under Benchmark
and the capability/runtime-policy views moved into the Benchmark body."""
from pathlib import Path


def _src():
    return Path("web/js/forge.js").read_text(encoding="utf-8")


def test_twin_assist_subtab_removed():
    source = _src()
    # No Twin Assist sub-tab / sub-nav anymore.
    assert 'data-bench-subtab="twin-assist"' not in source
    assert "data-twin-subtab" not in source
    assert "function twinAssistHtml" not in source


def test_capability_and_policy_views_live_in_benchmark():
    source = _src()
    assert "function capabilityPolicyHtml" in source
    assert "Capability &amp; runtime policy" in source
    assert "Twin Readiness" in source
    assert "Runtime Policy Preview" in source
    assert "Benchmark capability" in source
    # benchmarkHtml composes body + capability/policy.
    assert "_benchmarkBody(data) + capabilityPolicyHtml()" in source


def test_twin_result_renders_inline_under_benchmark():
    source = _src()
    assert "twinAssistInlineHtml" in source
    assert "Twin assist 評価（今回の実行）" in source


def test_subnav_css_present():
    css = Path("web/css/app.css").read_text(encoding="utf-8")
    assert ".forge-subnav{" in css
