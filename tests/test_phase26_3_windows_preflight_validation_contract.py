import unittest
from pathlib import Path


class TestPhase263WindowsPreflightValidationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = Path("docs/agent_guided_workflow_integration.md").read_text(encoding="utf-8")
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_preflight_success_note_exists_in_docs(self):
        for token in [
            "Phase 26.3 note",
            "Windows local backend preflight-only",
            "Total scenarios: 1",
            "PASS: 1",
            "atlas_backend_preflight",
            "/health 200",
            "errors []",
        ]:
            self.assertIn(token, self.docs)

    def test_default_mode_remains_9_ui_scenarios(self):
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

    def test_base_url_guard_remains(self):
        self.assertIn("PLAYWRIGHT_SMOKE_BASE_URL is ignored in default mock-backed UI smoke", self.smoke)
        self.assertIn("use_explicit_base_url=real_backend_opt_in", self.smoke)

    def test_preflight_only_remains_isolated(self):
        self.assertIn("UI scenarios skipped in preflight-only mode.", self.smoke)
        self.assertIn('scenarios = [("atlas_backend_preflight", run_backend_preflight)]', self.smoke)

    def test_no_diagnostic_post(self):
        self.assertNotIn("page.request.post(", self.smoke)
        self.assertNotIn("/api/task/plan diagnostic POST", self.smoke)

    def test_workflow_optins_disabled(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_PREFLIGHT=1", self.workflow)
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)


if __name__ == "__main__":
    unittest.main()
