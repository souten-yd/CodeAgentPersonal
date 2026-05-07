from pathlib import Path


def test_autopilot_ui_execution_preview_contract() -> None:
    ui = Path("ui.html").read_text(encoding="utf-8").lower()
    assert "prepare execution preview" in ui
    assert "requires approved atlas plan" in ui
    assert "preview only — no files will be changed" in ui
    assert "approval required before execution preview" in ui
    for token in ["execute task", "run task", "auto apply", "auto approve", "run all", "execute all"]:
        assert token not in ui
