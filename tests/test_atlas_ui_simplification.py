import re
from tests.helpers.ui_contract import load_ui_contract_text

UI = load_ui_contract_text()

def test_top_nav_still_has_atlas_but_no_agent():
    assert 'id="btn-chat"' in UI
    assert 'id="btn-atlas"' in UI
    assert 'id="btn-echo"' in UI
    assert 'id="btn-nexus"' in UI
    assert 'id="btn-agent"' not in UI

def test_atlas_submenu_is_simplified():
    for label in ['Start', 'Autopilot', 'Plan', 'History']:
        assert label in UI
    for label in ['Review', 'Execute', 'Patch', 'Runs']:
        pattern = rf'<button[^>]*(atlas-subview|data-atlas-subview)[^>]*>\s*{label}\s*</button>'
        assert not re.search(pattern, UI, flags=re.IGNORECASE)

def test_no_standalone_atlas_title_above_workbench():
    assert 'id="btn-atlas"' in UI
    forbidden_patterns = [
        r'<h1[^>]*>\s*Atlas\s*</h1>',
        r'<h2[^>]*>\s*Atlas\s*</h2>',
        r'<h3[^>]*>\s*Atlas\s*</h3>',
        r'<div[^>]*(?:id|class)="[^"]*(?:atlas-title|mode-title|panel-title|section-title|current-mode-title)[^"]*"[^>]*>\s*Atlas\s*</div>',
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, UI, flags=re.IGNORECASE)

def test_agent_advanced_compat_remains():
    assert 'Legacy Agent Advanced' in UI or 'Open Agent Advanced' in UI
    assert 'startAgentGuidedWorkflow' in UI

def test_no_dangerous_automation_added():
    lowered = UI.lower()
    for token in ['auto apply', 'auto approve', 'bulk apply', 'bulk approve', 'approval bypass']:
        assert token not in lowered
