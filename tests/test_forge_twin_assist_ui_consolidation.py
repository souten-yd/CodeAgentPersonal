"""UI consolidation: Twin Assist tab uses a sub-navigation instead of a card stack."""
from pathlib import Path


def test_twin_assist_uses_subnav_with_three_sections():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "forge-subnav" in source
    assert "data-twin-subtab" in source
    # The three consolidated sections.
    assert "['evaluation', 'Evaluation']" in source
    assert "['readiness', 'Readiness']" in source
    assert "['runtime-policy', 'Runtime Policy']" in source
    # Single coherent tab title.
    assert "forge-section-title\">Twin Assist<" in source


def test_twin_assist_subnav_is_wired_to_state():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "state.twinAssist.subtab = btn.getAttribute('data-twin-subtab')" in source
    assert "subtab: 'evaluation'" in source


def test_twin_assist_subnav_has_css():
    css = Path("web/css/app.css").read_text(encoding="utf-8")
    assert ".forge-subnav{" in css


def test_empty_states_present_for_unrun_sections():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    # Evaluation is now driven from the Benchmark action; the subtab is read-only.
    assert "まだ評価結果がありません。Benchmark タブで実行してください。" in source
    assert "Run a Twin Assist evaluation to populate Twin readiness" in source
