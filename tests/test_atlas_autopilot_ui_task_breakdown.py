from tests.helpers.ui_contract import load_ui_contract_text


def test_autopilot_ui_task_breakdown_sections_exist() -> None:
    ui = load_ui_contract_text()
    assert "Task Breakdown" in ui
    assert "Selected Architecture" in ui
    assert "Execution Order" in ui
    assert "Safety Notes" in ui
    assert "Preview only" in ui


def test_autopilot_ui_has_no_run_execute_apply_approve_all_buttons() -> None:
    ui = load_ui_contract_text().lower()
    for token in ["run all", "execute all", "auto apply", "auto approve"]:
        assert token not in ui
