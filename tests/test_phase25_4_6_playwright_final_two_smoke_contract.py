import unittest
from pathlib import Path


class TestPhase2546PlaywrightFinalTwoSmokeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_atlas_requirement_controls_are_workbench_root_scoped(self):
        self.assertIn("#atlas-workbench-card #atlas-requirement-use-chat-btn", self.smoke)
        self.assertIn("#atlas-workbench-card #atlas-requirement-clear-btn", self.smoke)
        self.assertIn("#atlas-workbench-card #atlas-requirement-input", self.smoke)
        self.assertNotIn("[data-atlas-subview-panel='overview'] #atlas-requirement-use-chat-btn", self.smoke)

    def test_atlas_start_uses_explicit_expected_text(self):
        self.assertIn('short_requirement_text = "Short Atlas requirement for smoke test"', self.smoke)
        self.assertIn('copied_requirement_text = "Copied from chat smoke"', self.smoke)
        self.assertIn('expected_text = copied_requirement_text', self.smoke)
        self.assertIn("await fill_atlas_requirement(page, expected_text)", self.smoke)

    def test_atlas_common_controls_do_not_require_overview_panel(self):
        self.assertNotIn("overview_panel.locator('#atlas-requirement-use-chat-btn')", self.smoke)
        self.assertNotIn("overview_panel.locator('#atlas-requirement-clear-btn')", self.smoke)

    def test_reference_card_accepts_current_viewer_text(self):
        self.assertIn("highlight: doc-1:0", self.smoke)
        self.assertIn("source_id: src-1", self.smoke)
        self.assertIn("mode: text", self.smoke)
        self.assertNotIn("includes('chunk:doc-1:0')", self.smoke)

    def test_reference_card_diagnostics_present(self):
        self.assertIn("cardButtonTexts", self.smoke)
        self.assertIn("viewerText", self.smoke)
        self.assertIn("openedUrls", self.smoke)

    def test_backend_e2e_remains_opt_in_and_non_destructive(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)
        lower = self.smoke.lower()
        for forbidden in ["approveplan(", "executepreview", "applypatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]:
            self.assertNotIn(forbidden, lower)


if __name__ == "__main__":
    unittest.main()
