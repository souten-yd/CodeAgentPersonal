"""The Forge Twin sub-tab is wired into ui.html and calls the /api/twin endpoints."""
from __future__ import annotations

from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui.html"


def test_twin_subtab_and_panel_present():
    html = UI.read_text(encoding="utf-8")
    assert 'data-forge-tab="twin"' in html          # sub-tab button
    assert 'id="tab-twin"' in html                   # panel container
    assert "function renderTwinPanel" in html        # renderer
    # switchForgeTab and relocateForgePanels include 'twin'
    assert "'overview', 'models', 'asr', 'tts', 'twin'" in html
    assert "'tab-models', 'tab-asr', 'tab-tts', 'tab-twin'" in html


def test_twin_panel_calls_twin_api():
    html = UI.read_text(encoding="utf-8")
    assert "/api/twin" in html
    assert "/settings" in html and "/profiles" in html and "/evaluate" in html
    # settings changes POST; evaluation POSTs a model id
    assert "twinSetSetting" in html and "twinRunEvaluation" in html
