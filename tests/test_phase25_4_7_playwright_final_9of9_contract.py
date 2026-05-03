import unittest
from pathlib import Path


class TestPhase2547PlaywrightFinal9of9Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_direct_chat_input_setter_exists(self):
        self.assertIn("async def set_chat_input_value_direct", self.smoke)

    def test_atlas_use_chat_input_stays_atlas_and_scoped(self):
        self.assertIn("await set_chat_input_value_direct(page, copied_requirement_text)", self.smoke)
        self.assertIn("await open_atlas(page)", self.smoke)
        self.assertIn("#atlas-workbench-card #atlas-requirement-use-chat-btn", self.smoke)

    def test_atlas_expected_variables_present(self):
        self.assertIn('copied_requirement_text = "Copied from chat smoke"', self.smoke)
        self.assertIn("expected_text = copied_requirement_text", self.smoke)

    def test_reference_viewer_current_fields(self):
        self.assertIn("highlight: doc-1:0", self.smoke)
        self.assertIn("source_id: src-1", self.smoke)
        self.assertIn("mode: text", self.smoke)

    def test_reference_card_no_stale_chunk_only_wait(self):
        self.assertNotIn("#nexus-deep-chunks-src-1", self.smoke)
        self.assertNotIn("includes('chunk:doc-1:0')", self.smoke)

    def test_reference_diagnostics_exist(self):
        self.assertIn("viewerText", self.smoke)
        self.assertIn("openedUrls", self.smoke)
        self.assertIn("cardButtonTexts", self.smoke)

    def test_backend_e2e_opt_in_gate_remains(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)

    def test_no_destructive_auto_actions(self):
        banned = [
            "approvePlan(",
            "executePreview",
            "applyPatch",
            "bulk apply",
            "bulk approve",
            "auto apply",
            "auto approve",
        ]
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
