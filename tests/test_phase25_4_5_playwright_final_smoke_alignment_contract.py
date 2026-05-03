import unittest
from pathlib import Path


class TestPhase2545PlaywrightFinalSmokeAlignmentContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_atlas_requirement_controls_root_scoped(self):
        self.assertIn("#atlas-workbench-card #atlas-requirement-use-chat-btn", self.smoke)
        self.assertIn("#atlas-workbench-card #atlas-requirement-clear-btn", self.smoke)
        self.assertNotIn("overview_panel.locator('#atlas-requirement-use-chat-btn')", self.smoke)

    def test_guided_workflow_no_longer_requires_final_chat_input_value(self):
        self.assertNotIn('assert await page.input_value("#input") == "Phase 25 smoke requirement text"', self.smoke)
        self.assertNotIn("chat input should sync from atlas requirement", self.smoke)
        self.assertIn("Requirement Preview: Phase 25 smoke requirement text", self.smoke)
        self.assertIn("BossPhase 25 smoke requirement text", self.smoke)

    def test_nexus_tabs_accept_missing_panel_when_button_active(self):
        self.assertIn("panelDisplay: panel ? getComputedStyle(panel).display : 'missing'", self.smoke)
        self.assertIn('allPanelIds', self.smoke)
        self.assertIn('assert "active" in diag["buttonClass"] and diag["nexusVisible"]', self.smoke)

    def test_reference_card_accepts_current_viewer_text(self):
        self.assertIn("highlight: doc-1:0", self.smoke)
        self.assertIn("source_id: src-1", self.smoke)
        self.assertIn("mode: text", self.smoke)
        self.assertNotIn("includes('chunk:doc-1:0')", self.smoke)

    def test_backend_e2e_remains_opt_in_and_non_destructive(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        lower = self.smoke.lower()
        for forbidden in ['approveplan(', 'executepreview', 'applypatch', 'bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
