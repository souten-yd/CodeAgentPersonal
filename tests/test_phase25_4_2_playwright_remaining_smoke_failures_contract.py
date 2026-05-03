import unittest
from pathlib import Path


class TestPhase2542PlaywrightRemainingSmokeFailuresContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_nexus_tabs_wait_for_function_uses_arg_keyword(self):
        self.assertIn("arg=tab", self.smoke)
        self.assertNotIn("\n      tab,\n    )", self.smoke)

    def test_atlas_use_chat_selector_scoped_under_atlas_workbench(self):
        self.assertIn("overview_panel = page.locator(\"#atlas-workbench-card [data-atlas-subview-panel='overview']\")", self.smoke)
        self.assertIn("use_chat_btn = overview_panel.locator('#atlas-requirement-use-chat-btn')", self.smoke)

    def test_chat_input_helper_hidden_fallback_exists(self):
        self.assertIn("async def set_chat_input", self.smoke)
        self.assertIn("dispatchEvent(new Event('input'", self.smoke)

    def test_mobile_viewport_and_isolation_present(self):
        self.assertIn("DEFAULT_MOBILE_VIEWPORT", self.smoke)
        self.assertIn("await browser.new_page(viewport=viewport or DEFAULT_DESKTOP_VIEWPORT)", self.smoke)

    def test_reference_card_actions_does_not_hard_require_stale_button(self):
        self.assertIn("if await web_scout_tab.count() > 0", self.smoke)
        self.assertIn("await page.click(\"#nexus-btn-sources\")", self.smoke)

    def test_summary_has_scenario_name_escaping_and_artifact(self):
        self.assertIn('escaped_name = scenario_name.replace("|"', self.smoke)
        self.assertIn("summary.md", self.smoke)
        self.assertIn("artifact", self.smoke)

    def test_backend_e2e_opt_in_and_non_destructive(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        lower = self.smoke.lower()
        for forbidden in ["approveplan(", "applypatch", "auto apply", "auto approve"]:
            self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
