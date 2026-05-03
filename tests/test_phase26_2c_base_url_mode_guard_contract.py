import unittest
from pathlib import Path


class TestPhase262cBaseUrlModeGuardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_default_mode_ignores_explicit_base_url(self):
        self.assertIn("PLAYWRIGHT_SMOKE_BASE_URL is ignored in default mock-backed UI smoke", self.smoke)
        self.assertIn("get_smoke_base_url(use_explicit_base_url=real_backend_opt_in)", self.smoke)

    def test_explicit_base_url_only_for_backend_optins(self):
        for token in [
            "run_backend_preflight_opt_in",
            "run_backend_e2e_opt_in",
            "real_backend_opt_in",
            "use_explicit_base_url: bool = False",
        ]:
            self.assertIn(token, self.smoke)

    def test_preflight_only_scenario_list(self):
        self.assertIn('scenarios = [("atlas_backend_preflight", run_backend_preflight)]', self.smoke)
        self.assertNotIn('scenarios = [("atlas_start_button_feedback"', self.smoke)

    def test_full_backend_e2e_scenario_list(self):
        self.assertIn('("atlas_backend_preflight", run_backend_preflight)', self.smoke)
        self.assertIn('("atlas_backend_e2e_journey", verify_atlas_backend_e2e_journey)', self.smoke)

    def test_default_mode_9_ui_plus_mobile(self):
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

    def test_preflight_is_get_only(self):
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
