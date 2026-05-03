import unittest
from pathlib import Path


class TestPhase25_4_12ReferenceViewerAsyncWaitContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_async_wait_helper_exists(self):
        self.assertIn("async def wait_reference_viewer_text_fields", self.smoke)

    def test_collect_helper_exists(self):
        self.assertIn("async def collect_reference_viewer_text", self.smoke)

    def test_full_text_click_before_wait(self):
        click_idx = self.smoke.find("click_reference_button(ref_card, [\"全文表示\"")
        wait_idx = self.smoke.find("wait_reference_viewer_text_fields(page, [\"source_id: src-1\", \"mode: text\"], \"Full Text\")", click_idx)
        self.assertGreater(click_idx, -1)
        self.assertGreater(wait_idx, click_idx)

    def test_fetched_urls_recorded_for_text(self):
        for token in ["window.__fetchedUrls = []", "fetchedUrls", "/nexus/sources/src-1/text"]:
            self.assertIn(token, self.smoke)

    def test_opened_urls_separated(self):
        for token in ["window.__openedUrls", "https://example.com/report", "/nexus/sources/src-1/original"]:
            self.assertIn(token, self.smoke)

    def test_current_viewer_fields_are_used(self):
        for token in ["source_id: src-1", "mode: text", "highlight: doc-1:0"]:
            self.assertIn(token, self.smoke)

    def test_text_url_not_required_in_opened_urls(self):
        self.assertIn("assert any(\"/nexus/sources/src-1/text\" in url for url in fetched_urls)", self.smoke)
        self.assertNotIn("assert any(\"/nexus/sources/src-1/text\" in url for url in opened_urls)", self.smoke)

    def test_backend_e2e_opt_in_remains(self):
        self.assertIn("RUN_ATLAS_BACKEND_E2E", self.smoke)

    def test_no_destructive_actions(self):
        forbidden = [
            "approvePlan(",
            "executePreview",
            "applyPatch",
            "bulk apply",
            "bulk approve",
            "auto apply",
            "auto approve",
        ]
        for token in forbidden:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
