import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "ui.html").read_text(encoding="utf-8")
CSS = (ROOT / "web/css/app.css").read_text(encoding="utf-8")


def _nexus_subtab_labels():
    topbar = re.search(r'<div class="nexus-subtabs">(?P<body>.*?)</div>', UI, re.S)
    assert topbar, "Nexus subtabs block not found"
    return re.findall(r'<button[^>]+class="nexus-subtab[^>]*"[^>]*>([^<]+)</button>', topbar.group("body"))


def test_nexus_subtabs_show_only_five_visible_tabs():
    assert _nexus_subtab_labels() == ["Research", "Library", "Evidence", "Reports", "Settings"]


def test_nexus_subtabs_remove_dashboard_and_sources_buttons():
    subtab_block = re.search(r'<div class="nexus-subtabs">(?P<body>.*?)</div>', UI, re.S).group("body")
    assert "Dashboard" not in subtab_block
    assert "Sources" not in subtab_block
    assert 'id="nexus-btn-dashboard"' not in subtab_block
    assert 'id="nexus-btn-sources"' not in subtab_block
    assert 'data-nexus-tab="dashboard"' not in subtab_block
    assert 'data-nexus-tab="sources"' not in subtab_block


def test_nexus_sources_dashboard_aliases_normalize_to_visible_tabs():
    assert "function normalizeNexusTabName(name)" in UI
    assert "if (raw === 'sources') return 'evidence';" in UI
    assert "if (raw === 'dashboard') return 'research';" in UI
    assert "const normalized = normalizeNexusTabName(name);" in UI
    assert "function showNexusTab(name)" in UI
    assert "const target = tabs.includes(normalized) ? normalized : 'research';" in UI


def test_evidence_tab_contains_sources_and_evidence_sections():
    assert '<div class="nexus-card-title">Evidence</div>' in UI
    assert "Sources are collected URLs/documents. Evidence is the subset of source chunks used as citations in answers." in UI
    assert '<div class="nexus-card-title">Used Evidence</div>' in UI
    assert '<div class="nexus-card-title">Collected Sources</div>' in UI
    assert '<div class="nexus-card-title">Actions</div>' in UI
    assert 'id="nexus-sources-results"' in UI
    assert 'id="nexus-evidence-result"' in UI


def test_mobile_nexus_tabs_grid_and_evidence_scroll_css_exist():
    assert "@media(max-width:768px)" in CSS
    assert ".nexus-subtabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr))" in CSS
    assert ".nexus-subtab{min-width:0;width:100%;padding:7px 4px;font-size:10px" in CSS
    assert "@media(max-width:360px)" in CSS
    assert ".nexus-subtabs{grid-template-columns:repeat(3,minmax(0,1fr))}" in CSS
    assert ".nexus-evidence-scroll{max-width:100%;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch}" in CSS
    assert ".nexus-evidence-scroll table{width:max-content;min-width:100%}" in CSS
