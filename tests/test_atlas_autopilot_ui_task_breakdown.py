from pathlib import Path


def test_autopilot_ui_task_breakdown_sections_exist() -> None:
    ui = Path("ui.html").read_text(encoding="utf-8")
    assert "Task Breakdown" in ui
    assert "Selected Architecture" in ui
    assert "Execution Order" in ui
    assert "Safety Notes" in ui
    assert "Preview only" in ui


def test_autopilot_ui_has_no_run_execute_apply_approve_all_buttons() -> None:
    ui = Path("ui.html").read_text(encoding="utf-8").lower()
    for token in ["run all", "execute all", "auto apply", "auto approve"]:
        assert token not in ui
