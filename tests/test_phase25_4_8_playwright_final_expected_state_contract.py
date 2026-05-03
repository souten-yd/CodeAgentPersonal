import unittest
from pathlib import Path


class TestPhase2548PlaywrightFinalExpectedStateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_atlas_start_feedback_is_staged(self):
        for token in [
            "# A. Empty start feedback",
            "# B. Persistence / clear",
            "# C. Use Chat Input",
            "# D. Atlas input Start",
            "# E. Chat fallback Start",
        ]:
            self.assertIn(token, self.smoke)

    def test_atlas_start_does_not_require_final_input_value(self):
        self.assertNotIn("atlasValue === 'Copied from chat smoke'", self.smoke)
        self.assertIn("Requirement Preview", self.smoke)

    def test_chat_fallback_is_accepted(self):
        self.assertIn("Falling back to Chat input.", self.smoke)

    def test_reference_viewer_current_fields(self):
        self.assertIn("source_id: src-1", self.smoke)
        self.assertIn("mode: text", self.smoke)
        self.assertIn("highlight: doc-1:0", self.smoke)

    def test_reference_does_not_require_old_chunk_wait(self):
        self.assertNotIn("#nexus-deep-chunks-src-1", self.smoke)
        self.assertNotIn("includes('chunk:doc-1:0')", self.smoke)

    def test_diagnostics_helpers_exist(self):
        self.assertIn("async def atlas_diag_dump", self.smoke)
        self.assertIn("async def ref_diag_dump", self.smoke)

    def test_backend_e2e_remains_opt_in(self):
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
