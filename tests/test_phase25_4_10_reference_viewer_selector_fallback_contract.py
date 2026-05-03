import unittest
from pathlib import Path


class TestPhase25410ReferenceViewerSelectorFallbackContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_reference_viewer_helper_exists(self):
        self.assertTrue(
            any(token in self.smoke for token in ["get_reference_viewer_text", "collect_reference_viewer_text"])
        )

    def test_selector_fallback_exists(self):
        for token in [
            "#nexus-reference-viewer",
            "#nexus-deep-reference-viewer",
            ".nexus-reference-viewer",
            "#nexus-col",
        ]:
            self.assertIn(token, self.smoke)

    def test_current_viewer_fields_are_used(self):
        for token in ["source_id: src-1", "mode: text", "highlight: doc-1:0"]:
            self.assertIn(token, self.smoke)

    def test_old_chunk_only_dependency_removed(self):
        self.assertNotIn("#nexus-deep-chunks-src-1", self.smoke)
        self.assertNotIn("includes('chunk:doc-1:0')", self.smoke)

    def test_viewer_wait_and_url_asserts_are_separated(self):
        self.assertIn("window.__openedUrls || []", self.smoke)
        for token in [
            "/nexus/sources/src-1/text",
            "https://example.com/report",
            "/nexus/sources/src-1/original",
        ]:
            self.assertIn(token, self.smoke)

    def test_diagnostics_include_candidate_dump_and_opened_urls(self):
        for token in ["selectorTextDump", "normalizedViewerText", "openedUrls"]:
            self.assertIn(token, self.smoke)

    def test_backend_e2e_remains_opt_in(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)

    def test_no_destructive_actions(self):
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
