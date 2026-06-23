from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATLAS_CLAUDE_PANEL_JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


def test_strategic_plan_step_cards_render_detail_fields_without_goal_gate() -> None:
    step_loop = ATLAS_CLAUDE_PANEL_JS.split("strategic.steps.forEach((s, i) => {", 1)[1].split("sec.appendChild(row);", 1)[0]
    assert "if (stepCount)" in ATLAS_CLAUDE_PANEL_JS
    assert "if (s.goal) para(row, `Goal: ${s.goal}`);" in step_loop
    assert "textItems(s.acceptance_criteria)" in step_loop
    assert "Verification: ${s.verification}" in step_loop
    assert "Rollback: ${s.rollback}" in step_loop
    assert "files: ${s.target_files.join(', ')}" in step_loop


def test_strategic_plan_card_prefers_english_plan_labels_and_canonical_details() -> None:
    assert "Strategic plan - ${stepCount} execution steps" in ATLAS_CLAUDE_PANEL_JS
    assert "Execution Steps" in ATLAS_CLAUDE_PANEL_JS
    assert "Acceptance criterion: ${x}" in ATLAS_CLAUDE_PANEL_JS
    assert "Original request and canonical task" in ATLAS_CLAUDE_PANEL_JS
    assert "Raw plan details" in ATLAS_CLAUDE_PANEL_JS
