import unittest
from pathlib import Path


class TestPhase25_4_14ReferenceCardActionSequenceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_full_text_action_requires_fetch_not_highlight(self):
        for token in ["全文表示", "/nexus/sources/src-1/text", "source_id: src-1", "mode: text"]:
            self.assertIn(token, self.smoke)
        self.assertIn('"Full Text"', self.smoke)

    def test_highlight_action_is_separate(self):
        self.assertIn("該当箇所", self.smoke)
        self.assertIn('wait_reference_viewer_text_fields(page, ["doc-1:0"], "Highlight")', self.smoke)

    def test_url_action_is_separate(self):
        self.assertIn("元URL", self.smoke)
        self.assertIn("https://example.com/report", self.smoke)

    def test_download_action_is_separate(self):
        self.assertIn("ダウンロード", self.smoke)
        self.assertIn("/nexus/sources/src-1/original", self.smoke)

    def test_fetched_opened_separation(self):
        for token in ["__fetchedUrls", "__openedUrls"]:
            self.assertIn(token, self.smoke)

    def test_action_label_diagnostics_and_backend_gate(self):
        for token in ["Full Text", "Highlight", "Source URL", "Download", "RUN_ATLAS_BACKEND_E2E"]:
            self.assertIn(token, self.smoke)

    def test_no_destructive_actions(self):
        banned = ["approvePlan(", "executePreview", "applyPatch", "bulk apply", "bulk approve", "auto apply", "auto approve"]
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
