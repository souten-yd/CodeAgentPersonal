from tests.helpers.ui_contract import load_ui_contract_text


def test_top_nav_agent_button_removed_and_core_modes_exist():
    text = load_ui_contract_text()
    assert 'id="btn-chat"' in text
    assert 'id="btn-atlas"' in text
    assert 'id="btn-echo"' in text
    assert 'id="btn-nexus"' in text
    assert 'id="btn-agent"' not in text


def test_agent_advanced_and_compat_functions_remain():
    text = load_ui_contract_text()
    assert "Legacy Agent Advanced" in text
    assert "startAgentGuidedWorkflow" in text


def test_no_forbidden_auto_apply_or_approval_bypass_added():
    text = load_ui_contract_text().lower()
    assert "auto apply" not in text
    assert "auto approve" not in text
    assert "bulk apply" not in text
    assert "approval bypass" not in text
