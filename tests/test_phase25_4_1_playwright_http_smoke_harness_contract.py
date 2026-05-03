import unittest
from pathlib import Path


class TestPhase2541PlaywrightHttpSmokeHarnessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
        cls.workflow = Path(".github/workflows/playwright-ui-smoke.yml").read_text(encoding="utf-8")

    def test_file_scheme_not_used_for_smoke_base(self):
        self.assertNotIn("as_uri()", self.smoke)
        self.assertNotIn("file://", self.smoke)

    def test_http_mock_server_exists(self):
        for token in ["ThreadingHTTPServer", "127.0.0.1", '"/settings"', '"/health"', '"/system/summary"', '"/api/task/plan"']:
            self.assertIn(token, self.smoke)

    def test_scenario_isolation_exists(self):
        self.assertIn("await browser.new_page", self.smoke)
        self.assertIn("await page.close()", self.smoke)
        self.assertIn("DEFAULT_DESKTOP_VIEWPORT", self.smoke)
        self.assertIn("DEFAULT_MOBILE_VIEWPORT", self.smoke)

    def test_chat_input_helpers_exist(self):
        self.assertIn("async def set_chat_input", self.smoke)
        self.assertIn("async def get_chat_input_value", self.smoke)

    def test_summary_and_artifact_improvements_exist(self):
        self.assertIn("summary.md", self.smoke)
        self.assertIn("PLAYWRIGHT_ARTIFACT_DIR", self.smoke)
        self.assertIn(".log", self.smoke)

    def test_workflow_artifact_upload_and_step_summary_exist(self):
        self.assertIn("uses: actions/upload-artifact@v4", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("$GITHUB_STEP_SUMMARY", self.workflow)

    def test_backend_e2e_default_stays_off(self):
        self.assertNotIn("RUN_ATLAS_BACKEND_E2E=1", self.workflow)

    def test_no_destructive_actions(self):
        lower = (self.smoke + "\n" + self.workflow).lower()
        for forbidden in ["approveplan(", "executepreview", "applypatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]:
            self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
