"""Arena/Twin assist-effect radar: visualize Twin effect with vs without assist."""
from pathlib import Path


def test_assist_effect_radar_renderer_present():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "function assistEffectRadarHtml" in source
    # Two overlaid series: with assist (assisted) and without assist (baseline).
    assert "forge-radar-shape--assisted" in source
    assert "forge-radar-shape--baseline" in source
    assert "ring('baseline')" in source and "ring('assisted')" in source
    # Legend communicates the with/without-assist (補助有無) meaning.
    assert "with assist (補助あり)" in source
    assert "without assist (補助なし)" in source
    # Driven by real baseline vs assisted comparison data.
    assert "c.baseline" in source and "c.best_score" in source
    assert "escapeHtml(entry.key)" in source


def test_assist_effect_radar_shown_in_results():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "Assist Effect (補助有無)" in source
    assert "assistEffectRadarHtml(report.comparisons)" in source


def test_assist_effect_radar_has_css():
    css = Path("web/css/app.css").read_text(encoding="utf-8")
    assert ".forge-radar-shape--baseline{" in css
    assert ".forge-radar-shape--assisted{" in css
    assert ".forge-radar-legend{" in css
