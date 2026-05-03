import re
import unittest
from pathlib import Path


class TestPhase25AtlasGuidedWorkflowE2EContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path("ui.html").read_text(encoding="utf-8")
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_safe_journey_function_exists(self):
        self.assertIn("async def verify_atlas_guided_workflow_safe_journey(page) -> None:", self.smoke)

    def test_status_fields_exist(self):
        for token in [
            "Source:",
            "Workspace:",
            "Requirement Source:",
            "Requirement Preview:",
            "Last Error:",
        ]:
            self.assertIn(token, self.ui)

    def test_plan_workflow_state_fields_exist_or_referenced(self):
        for token in ["requirementSource", "requirementTextPreview", "lastError"]:
            self.assertIn(token, self.ui)

    def test_guided_plan_flow_sections_exist(self):
        for token in [
            "Atlas Guided Plan Flow",
            "Requirement",
            "Plan",
            "Review",
            "Approval",
            "Execute Preview",
            "Patch Review",
        ]:
            self.assertIn(token, self.ui)

    def test_action_buttons_remain_non_destructive(self):
        m = re.search(r"function renderAtlasPlanNextActionButtons\(flow\) \{([\s\S]*?)\n\}", self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("focusAtlasWorkflowSection('review')", body)
        self.assertIn("focusAtlasWorkflowSection('approval')", body)
        self.assertIn("focusAtlasWorkflowSection('execute_preview')", body)
        self.assertIn("openPatchReviewFromWorkbench", body)

    def test_no_direct_unsafe_execution_in_smoke(self):
        lower = self.smoke.lower()
        for forbidden in [
            "approveplan(",
            "executepreview",
            "applypatch",
            "fetch('/api/execute-preview')",
            "bulk apply",
            "bulk approve",
            "auto apply",
            "auto approve",
        ]:
            self.assertNotIn(forbidden, lower)

    def test_restore_no_auto_fetch_remains(self):
        m = re.search(r"function restoreAtlasSubviewState\(\) \{([\s\S]*?)\n\}", self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertNotIn("loadRecentAtlasRunsFromWorkbench", body)
        self.assertNotIn("openManualAtlasRunDashboardFromWorkbench", body)
        self.assertNotIn("loadPhase8Patches", body)

    def test_generate_plan_only_from_input_legacy_safe(self):
        m = re.search(r"async function generatePlanOnlyFromInput\(\) \{([\s\S]*?)\n\}", self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertNotIn("options?.requirementText", body)
        self.assertNotIn("source === 'atlas'", body)
        self.assertNotIn("deriveAtlasRequirementSource", body)


if __name__ == "__main__":
    unittest.main()
