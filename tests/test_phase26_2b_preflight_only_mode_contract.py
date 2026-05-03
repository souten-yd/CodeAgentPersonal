import unittest
from pathlib import Path


class TestPhase262bPreflightOnlyModeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_mode_detection_flags_exist(self):
        for token in [
            "run_backend_preflight_opt_in",
            "run_backend_e2e_opt_in",
            "preflight_only_mode",
            "full_backend_e2e_mode",
        ]:
            self.assertIn(token, self.smoke)

    def test_preflight_only_scenarios_exclude_default_ui(self):
        self.assertIn('scenarios = [("atlas_backend_preflight", run_backend_preflight)]', self.smoke)
        self.assertIn("UI scenarios skipped in preflight-only mode", self.smoke)
        self.assertNotIn('scenarios = [("atlas_start_button_feedback"', self.smoke)

    def test_full_backend_e2e_scenario_list_is_separate(self):
        self.assertIn('(\"atlas_backend_preflight\", run_backend_preflight)', self.smoke)
        self.assertIn('(\"atlas_backend_e2e_journey\", verify_atlas_backend_e2e_journey)', self.smoke)
        self.assertIn("default UI scenarios are skipped in full backend E2E mode", self.smoke)

    def test_default_mode_still_contains_9_ui_scenarios(self):
        for token in [
            "bootstrap_api_contract",
            "mode_switches",
            "atlas_start_button_feedback",
            "atlas_guided_workflow_safe_journey",
            "mode_specific_subtabs",
            "nexus_tabs",
            "reference_card_actions",
            "chat_search_and_agent_web_tool_tts",
            "mobile_mode_switches",
        ]:
            self.assertIn(token, self.smoke)

    def test_preflight_remains_get_only(self):
        self.assertIn("page.request.get(", self.smoke)
        self.assertNotIn("page.request.post(", self.smoke)
        self.assertNotIn("/api/task/plan diagnostic POST", self.smoke)

    def test_workflow_does_not_enable_optins(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_PREFLIGHT=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)

    def test_no_destructive_actions(self):
        for token in ["approvePlan(", "executePreview", "applyPatch", "auto approve", "auto apply"]:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
