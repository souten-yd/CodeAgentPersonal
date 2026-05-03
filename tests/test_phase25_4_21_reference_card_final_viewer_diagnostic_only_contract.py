import unittest
from pathlib import Path


class TestPhase25421ReferenceCardFinalViewerDiagnosticOnlyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_final_viewer_required_assert_removed(self):
        self.assertNotIn('wait_reference_viewer_text_fields(page, ["source_id: src-1", "mode: text", "doc-1:0"], "Final")', self.smoke)
        self.assertNotIn('assert "mode: text" in viewer_text, viewer_text', self.smoke)
        self.assertNotIn('assert "highlight: doc-1:0" in viewer_text, viewer_text', self.smoke)

    def test_final_check_is_diagnostic_only(self):
        self.assertIn('await ref_diag_dump("final")', self.smoke)

    def test_full_text_and_highlight_required_checks_remain(self):
        self.assertIn('wait_reference_viewer_text_fields(page, ["source_id: src-1", "mode: text"], "Full Text")', self.smoke)
        self.assertIn('wait_reference_viewer_text_fields(page, ["doc-1:0"], "Highlight")', self.smoke)

    def test_source_url_and_download_stay_diagnostic_only(self):
        self.assertIn('Source URL is diagnostic-only', self.smoke)
        self.assertIn('Download action inspected only; not clicked to avoid current-page navigation in UI smoke.', self.smoke)
        self.assertNotIn('/nexus/sources/src-1/original" in url for url in tracking["fetchedUrls"]', self.smoke)
        self.assertNotIn('/nexus/sources/src-1/original" in url for url in fetched_urls', self.smoke)

    def test_backend_e2e_opt_in_and_no_destructive_actions(self):
        self.assertIn('RUN_ATLAS_BACKEND_E2E', self.smoke)
        for token in ['approvePlan(', 'executePreview', 'applyPatch', 'bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
