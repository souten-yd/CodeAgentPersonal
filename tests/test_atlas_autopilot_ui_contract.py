from pathlib import Path


def test_autopilot_subview_exists_and_preview_only_label() -> None:
    ui = Path("ui.html").read_text(encoding="utf-8")
    assert 'data-atlas-subview-panel="autopilot"' in ui
    assert "Preview only" in ui


def test_autopilot_ui_has_no_dangerous_auto_actions() -> None:
    ui = Path("ui.html").read_text(encoding="utf-8").lower()
    for token in [">auto apply<", ">auto-apply<", ">auto approve<", ">auto-approve<", ">auto delete<", ">auto-delete<"]:
        assert token not in ui
