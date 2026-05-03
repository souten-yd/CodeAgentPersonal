import unittest
from pathlib import Path


class TestPhase25415ReferenceCardHighlightClickContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_highlight_action_click_and_assert_remain(self):
        for token in [
            "clicked_action_button = await click_reference_button(ref_card, [\"該当箇所\"",
            "await wait_reference_viewer_text_fields(page, [\"doc-1:0\"], \"Highlight\")",
            "highlight: doc-1:0",
        ]:
            self.assertIn(token, self.smoke)

    def test_full_text_and_download_still_present(self):
        for token in ["全文表示", "/nexus/sources/src-1/text", "ダウンロード", "/nexus/sources/src-1/original"]:
            self.assertIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
