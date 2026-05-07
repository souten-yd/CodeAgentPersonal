from tests.helpers.ui_contract import load_ui_contract_text


def test_autopilot_button_wiring_and_status_copy() -> None:
    ui = load_ui_contract_text().lower()

    assert 'onclick="generateautopilottaskplan(this)"' in ui
    assert 'onclick="prepareautopilotexecutionpreview(this)"' in ui

    assert '/api/atlas/autopilot/' in ui
    assert '/tasks/' in ui
    assert '/plan' in ui
    assert '/execution-preview' in ui

    assert 'generating plan...' in ui
    assert 'preparing execution preview...' in ui

    assert "st === 'approval_required'" in ui
    assert "st === 'plan_required'" in ui
    assert "st === 'execution_preview_ready'" in ui

    banned_button_labels = [
        '>run task<',
        '>execute task<',
        '>run all<',
        '>execute all<',
        '>auto apply<',
        '>auto approve<',
        '>apply patch<',
    ]
    for phrase in banned_button_labels:
        assert phrase not in ui
