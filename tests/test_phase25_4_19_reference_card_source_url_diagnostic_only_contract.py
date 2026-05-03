import unittest
from pathlib import Path


class TestPhase25419ReferenceCardSourceUrlDiagnosticOnlyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_source_url_opened_urls_required_assert_removed(self):
        forbidden = [
            'if source_url_clicked:\n      assert source_url_opened, tracking',
            'if source_url_action_status == "clicked":\n    assert any("https://example.com/report" in url for url in opened_urls), opened_urls',
            'assert any("https://example.com/report" in url for url in tracking["openedUrls"])',
        ]
        for token in forbidden:
            self.assertNotIn(token, self.smoke)

    def test_source_url_action_diagnostic_only_statuses_exist(self):
        for token in [
            'source_url_action_status = "opened"',
            'clickedNoOpen',
            'source_url_action_status = "skippedDisabled"',
            'source_url_action_status = "skippedMissing"',
        ]:
            self.assertIn(token, self.smoke)

    def test_required_checks_preserved(self):
        for token in [
            '/nexus/sources/src-1/text',
            '/nexus/sources/src-1/chunks',
            'source_id: src-1',
            'mode: text',
            'doc-1:0',
        ]:
            self.assertIn(token, self.smoke)

    def test_button_state_diagnostics_preserved(self):
        for token in ['sourceUrlButtonState', 'onclick', 'disabled', 'enabled']:
            self.assertIn(token, self.smoke)

    def test_backend_e2e_opt_in_preserved(self):
        self.assertIn('RUN_ATLAS_BACKEND_E2E', self.smoke)

    def test_destructive_actions_not_added(self):
        banned = ['approvePlan(', 'executePreview', 'applyPatch', 'bulk apply', 'bulk approve', 'auto apply', 'auto approve']
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
