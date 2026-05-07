from pathlib import Path


def test_top_nav_agent_button_removed_and_core_modes_exist():
    text = Path("ui.html").read_text(encoding="utf-8")
    assert 'id="btn-chat"' in text
    assert 'id="btn-atlas"' in text
    assert 'id="btn-echo"' in text
    assert 'id="btn-nexus"' in text
    assert 'id="btn-agent"' not in text


def test_agent_advanced_and_compat_functions_remain():
    text = Path("ui.html").read_text(encoding="utf-8")
    assert "Legacy Agent Advanced" in text
    assert "startAgentGuidedWorkflow" in text


def test_no_forbidden_auto_apply_or_approval_bypass_added():
    text = Path("ui.html").read_text(encoding="utf-8").lower()
    assert "auto apply" not in text
    assert "auto approve" not in text
    assert "bulk apply" not in text
    assert "approval bypass" not in text
