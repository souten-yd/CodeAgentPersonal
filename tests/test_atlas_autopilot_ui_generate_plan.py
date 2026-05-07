from tests.helpers.ui_contract import load_ui_contract_text


def test_autopilot_ui_generate_plan_contract() -> None:
    ui = load_ui_contract_text().lower()
    assert "generate plan" in ui
    assert "plan only — no files will be changed" in ui
    assert "open plan" in ui
    assert "plan: -" in ui
    for token in ["run task", "execute task", "run all", "execute all", "auto apply", "auto approve"]:
        assert token not in ui
