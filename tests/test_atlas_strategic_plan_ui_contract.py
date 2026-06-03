from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATLAS_CLAUDE_PANEL_JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


def test_strategic_plan_step_cards_render_detail_fields_without_goal_gate() -> None:
    step_loop = ATLAS_CLAUDE_PANEL_JS.split("strategic.steps.forEach((s, i) => {", 1)[1].split("sec.appendChild(row);", 1)[0]
    assert "if (stepCount)" in ATLAS_CLAUDE_PANEL_JS
    assert "if (s.goal) para(row, `ゴール: ${s.goal}`);" in step_loop
    assert "textItems(s.acceptance_criteria)" in step_loop
    assert "検証: ${s.verification}" in step_loop
    assert "ロールバック: ${s.rollback}" in step_loop
    assert "files: ${s.target_files.join(', ')}" in step_loop
