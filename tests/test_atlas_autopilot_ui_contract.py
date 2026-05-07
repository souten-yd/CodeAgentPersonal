from tests.helpers.ui_contract import load_ui_contract_text


def test_autopilot_subview_exists_and_preview_only_label() -> None:
    ui = load_ui_contract_text()
    assert 'data-atlas-subview-panel="autopilot"' in ui
    assert "Preview only" in ui


def test_autopilot_ui_has_no_dangerous_auto_actions() -> None:
    ui = load_ui_contract_text().lower()
    for token in [">auto apply<", ">auto-apply<", ">auto approve<", ">auto-approve<", ">auto delete<", ">auto-delete<"]:
        assert token not in ui
