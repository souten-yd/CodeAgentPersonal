import unittest
from pathlib import Path


class TestPhase25_4_13ReferenceCardActionsSplitContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_helper_names_exist(self):
        for token in [
            "click_reference_button",
            "collect_reference_viewer_text",
            "wait_reference_viewer_text_fields",
            "get_reference_tracking",
        ]:
            self.assertIn(token, self.smoke)

    def test_full_text_wait_excludes_highlight(self):
        self.assertIn('wait_reference_viewer_text_fields(page, ["source_id: src-1", "mode: text"], "Full Text")', self.smoke)
        self.assertNotIn('wait_reference_viewer_text_fields(page, ["source_id: src-1", "mode: text", "highlight: doc-1:0"], "Full Text")', self.smoke)


if __name__ == "__main__":
    unittest.main()
