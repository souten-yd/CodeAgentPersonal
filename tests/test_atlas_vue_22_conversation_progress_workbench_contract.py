from pathlib import Path


def test_vue_conversation_workbench_components_are_mounted() -> None:
    app = Path("web/atlas-next/src/components/AtlasNextApp.vue").read_text(encoding="utf-8")

    for marker in [
        "ConversationWorkbench",
        "ProgressRail",
        "workbench-layout",
        "conversation-column",
        "guided-flow",
        "Guided Atlas requirement flow",
    ]:
        assert marker in app
    assert app.index("<RequirementInput />") < app.index("<ConversationWorkbench />")
    assert app.index("<section class=\"guided-flow\"") < app.index("<WorkflowReviewBoard :snapshot=\"snapshot\" />")


def test_conversation_workbench_supports_plan_operation_questions_and_details() -> None:
    text = Path("web/atlas-next/src/components/ConversationWorkbench.vue").read_text(encoding="utf-8")

    for marker in [
        "Atlas Conversation",
        "Plan setting",
        "Operation setting",
        "Questions for Atlas",
        "Detailed definition",
        "Requirement summary",
        "planModeLabel",
        "operationModeLabel",
        "questionsSummary",
        "detailsSummary",
        "Plan metadata only",
        "Backend authoritative",
        "Vue execution disabled",
    ]:
        assert marker in text

    forbidden = text.lower()
    for token in [
        "executeactionenabled: true",
        "applyactionenabled: true",
        "approvalactionenabled: true",
        "safe_apply(",
        "@router.post",
        "fetch(",
        "@click",
    ]:
        assert token not in forbidden


def test_progress_rail_tracks_workflow_without_enabling_execution() -> None:
    text = Path("web/atlas-next/src/components/ProgressRail.vue").read_text(encoding="utf-8")

    for marker in [
        "Atlas progress",
        "Requirement",
        "Plan",
        "Review",
        "Execute Preview",
        "Guarded Execute",
        "Safety locks",
        "Vue execution controls disabled",
    ]:
        assert marker in text

    assert "Requires explicit approval, dry-run evidence, and backend gate checks" in text
    assert "diagnostics.source === 'safe_get_adapter'" in text
    assert "latestRequirementId" in text
    assert "executionEnabled: true" not in text
    assert "autonomousExecutionEnabled: true" not in text
