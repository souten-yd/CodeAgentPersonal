import unittest
from pathlib import Path


class TestPhase2549PlaywrightFinalWaitContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_wait_for_function_uses_arg_keyword_for_js_args(self):
        self.assertIn("arg=[empty_start, empty_status]", self.smoke)
        self.assertIn("arg=[expected_text]", self.smoke)
        self.assertIn("arg=[atlas_start_value]", self.smoke)
        self.assertNotIn('}""", [empty_start, empty_status])', self.smoke)

    def test_reference_card_waits_for_current_viewer_fields(self):
        for token in ["source_id: src-1", "mode: text", "highlight: doc-1:0"]:
            self.assertIn(token, self.smoke)

    def test_reference_card_does_not_use_old_chunk_only_wait(self):
        self.assertNotIn("#nexus-deep-chunks-src-1", self.smoke)
        self.assertNotIn("includes('chunk:doc-1:0')", self.smoke)

    def test_reference_url_actions_are_still_checked(self):
        for token in [
            "/nexus/sources/src-1/text",
            "https://example.com/report",
            "/nexus/sources/src-1/original",
        ]:
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
