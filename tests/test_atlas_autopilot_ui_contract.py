from tests.helpers.ui_contract import load_ui_contract_text


def test_autopilot_subview_exists_and_preview_only_label() -> None:
    ui = load_ui_contract_text()
    assert 'data-atlas-subview-panel="autopilot"' in ui
    assert "Preview only" in ui


def test_autopilot_ui_has_no_dangerous_auto_actions() -> None:
    ui = load_ui_contract_text().lower()
    for token in [">auto apply<", ">auto-apply<", ">auto approve<", ">auto-approve<", ">auto delete<", ">auto-delete<"]:
        assert token not in ui


def test_autonomous_codegen_ui_uses_backend_normalized_state() -> None:
    ui = load_ui_contract_text()
    assert "getAutonomousCodegenStatus" in ui
    assert "/api/atlas/autonomous-codegen/status/" in ui
    assert "renderAutonomousWorkflowState" in ui
    assert "renderAutonomousWorkflowSummary" in ui
    assert "renderAutonomousSubPhaseTimeline" in ui
    assert "evidence.item_sub_phases" in ui
    assert "atlas-autonomous-subphase-timeline" in ui
    assert "decision_targets" in ui
    assert "user_visible_warnings" in ui
    assert "raw_json_included" not in ui


def test_profile_and_plan_visibility_contract() -> None:
    ui = load_ui_contract_text()
    assert "3: Autonomous（毎回 bounds 指定・完全自動 OFF）" in ui
    assert "4: Autonomous（envelope 内で完全自動・★完全自動コード生成）" in ui
    assert "full_auto=" in ui
    assert "acceptance_criteria" in ui
    assert "Raw plan" in ui
    assert "未解決" in ui
