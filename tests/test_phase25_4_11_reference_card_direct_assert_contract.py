import unittest
from pathlib import Path


class TestPhase25411ReferenceCardDirectAssertContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_direct_evaluate_helper_exists(self):
        self.assertTrue(any(token in self.smoke for token in ["collect_reference_viewer_text", "wait_reference_viewer_current_fields"]))

    def test_nexus_col_fallback_exists(self):
        self.assertIn("#nexus-col", self.smoke)

    def test_current_viewer_fields_asserted(self):
        for token in ["[S1] Mock Source", "source_id: src-1", "mode: text", "highlight: doc-1:0"]:
            self.assertIn(token, self.smoke)

    def test_old_chunk_wait_removed(self):
        self.assertNotIn("#nexus-deep-chunks-src-1", self.smoke)
        self.assertNotIn("includes('chunk:doc-1:0')", self.smoke)

    def test_viewer_wait_and_url_assert_separated(self):
        self.assertIn("openedUrls", self.smoke)
        for token in ["/nexus/sources/src-1/text", "https://example.com/report", "/nexus/sources/src-1/original"]:
            self.assertIn(token, self.smoke)

    def test_diagnostics_tokens_present(self):
        for token in ["normalizedText", "cardButtonTexts", "openedUrls", "activeNexusTab"]:
            self.assertIn(token, self.smoke)

    def test_backend_e2e_opt_in(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)

    def test_no_destructive_actions(self):
        banned = ["approvePlan(", "executePreview", "applyPatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
