import unittest
from pathlib import Path


class TestPhase25412ReferenceViewerEvaluateSyntaxContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_collect_reference_viewer_text_exists(self):
        self.assertIn("collect_reference_viewer_text", self.smoke)

    def test_collect_reference_viewer_uses_arg_keyword(self):
        self.assertIn('arg=REFERENCE_VIEWER_SELECTORS', self.smoke)

    def test_js_newline_literal_is_safe(self):
        self.assertIn("String.fromCharCode(10)", self.smoke)
        self.assertNotIn("join('\\n')", self.smoke)

    def test_current_viewer_fields_remain(self):
        for token in ["[S1] Mock Source", "source_id: src-1", "mode: text", "highlight: doc-1:0"]:
            self.assertIn(token, self.smoke)

    def test_old_chunk_only_dependency_remains_removed(self):
        self.assertNotIn("#nexus-deep-chunks-src-1", self.smoke)
        self.assertNotIn("chunk:doc-1:0", self.smoke)

    def test_diagnostics_remain(self):
        for token in ["candidates", "selectorTextDump", "normalizedText", "openedUrls", "activeNexusTab"]:
            self.assertIn(token, self.smoke)

    def test_backend_e2e_opt_in(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)

    def test_no_destructive_actions(self):
        banned = ["approvePlan(", "executePreview", "applyPatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
