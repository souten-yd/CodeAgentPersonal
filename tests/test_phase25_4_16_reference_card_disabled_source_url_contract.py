import unittest
from pathlib import Path


class TestPhase25416ReferenceCardDisabledSourceUrlContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_mock_source_includes_multiple_url_fields(self):
        for token in ["url: 'https://example.com/report'", "source_url: 'https://example.com/report'", "original_url: 'https://example.com/report'", "final_url: 'https://example.com/report'", "link: 'https://example.com/report'"]:
            self.assertIn(token, self.smoke)

    def test_source_url_button_click_is_enabled_only(self):
        self.assertIn("click_reference_button_if_enabled", self.smoke)
        self.assertIn("if await button.is_disabled():", self.smoke)
        self.assertNotIn("force=True", self.smoke)

    def test_source_url_assert_is_conditional(self):
        self.assertIn("source_url_action_status = \"skippedDisabled\"", self.smoke)
        self.assertIn("INFO: Source URL action skipped: button disabled", self.smoke)

    def test_full_text_highlight_and_download_remain(self):
        for token in ["全文表示", "該当箇所", "/nexus/sources/src-1/text", "highlight: doc-1:0", "ダウンロード", "/nexus/sources/src-1/original"]:
            self.assertIn(token, self.smoke)

    def test_diagnostics_include_button_state(self):
        for token in ["cardButtonTexts", "cardButtons", "disabled", "onclick"]:
            self.assertIn(token, self.smoke)

    def test_backend_e2e_gate_remains_opt_in(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)

    def test_destructive_actions_not_added(self):
        banned = ["approvePlan(", "executePreview", "applyPatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
