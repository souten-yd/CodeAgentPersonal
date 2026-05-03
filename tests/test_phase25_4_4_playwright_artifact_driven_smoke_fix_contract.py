import unittest
from pathlib import Path


class TestPhase2544PlaywrightArtifactDrivenSmokeFixContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_mode_switches_legacy_expectation_updated(self):
        self.assertIn('Open Legacy Task', self.smoke)
        self.assertIn('Open Agent Advanced', self.smoke)

    def test_atlas_helpers_exist(self):
        for name in [
            'async def open_atlas',
            'async def set_atlas_subview',
            'async def wait_atlas_subview',
            'async def ensure_atlas_overview',
            'async def ensure_atlas_plan',
        ]:
            self.assertIn(name, self.smoke)

    def test_atlas_start_feedback_uses_overview_guard(self):
        self.assertIn('await ensure_atlas_overview(page)', self.smoke)

    def test_guided_workflow_waits_or_logs_sync(self):
        self.assertIn("wait_for_function(", self.smoke)
        self.assertIn("chat input sync failed after atlas start", self.smoke)
        self.assertNotIn('assert await page.input_value("#input") == "Phase 25 smoke requirement text"', self.smoke)

    def test_nexus_tab_timeout_diagnostics(self):
        self.assertIn('nexus tab wait timeout diagnostics', self.smoke)
        self.assertIn('buttonClass', self.smoke)
        self.assertIn('panelDisplay', self.smoke)

    def test_reference_card_not_single_label_only(self):
        self.assertIn('click_first_visible_button_by_names', self.smoke)
        self.assertIn('"Show Full Text"', self.smoke)

    def test_mobile_mode_does_not_require_mob_agent_chat_active(self):
        self.assertNotIn("mob-agent-chat')?.classList.contains('active')", self.smoke)
        self.assertIn("getComputedStyle(chat).display !== 'none'", self.smoke)

    def test_backend_e2e_opt_in_and_non_destructive(self):
        self.assertIn('RUN_ATLAS_BACKEND_E2E', self.smoke)
        lower = self.smoke.lower()
        for forbidden in ['approveplan(', 'executepreview', 'applypatch', 'bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(forbidden, lower)


if __name__ == '__main__':
    unittest.main()
