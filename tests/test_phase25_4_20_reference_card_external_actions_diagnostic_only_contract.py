import unittest
from pathlib import Path


class TestPhase25420ReferenceCardExternalActionsDiagnosticOnlyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_source_url_action_is_diagnostic_only(self):
        self.assertIn('sourceUrlActionStatus', self.smoke)
        self.assertNotIn('assert any("https://example.com/report" in url for url in opened_urls)', self.smoke)
        self.assertNotIn('assert any("https://example.com/report" in url for url in tracking["openedUrls"])', self.smoke)

    def test_download_action_is_diagnostic_only(self):
        self.assertIn('downloadActionStatus', self.smoke)
        self.assertIn('Download action inspected only; not clicked to avoid current-page navigation in UI smoke.', self.smoke)
        self.assertNotIn('assert any("/nexus/sources/src-1/original" in url for url in tracking["openedUrls"])', self.smoke)
        self.assertNotIn('assert any("/nexus/sources/src-1/original" in url for url in opened_urls)', self.smoke)

    def test_full_text_and_highlight_checks_remain_required(self):
        for token in [
            '/nexus/sources/src-1/text',
            '/nexus/sources/src-1/chunks',
            'source_id: src-1',
            'mode: text',
            'doc-1:0',
            'highlight: doc-1:0',
        ]:
            self.assertIn(token, self.smoke)

    def test_button_state_diagnostics_exist(self):
        for token in ['sourceUrlButtonState', 'downloadButtonState', 'onclick', 'disabled', 'enabled']:
            self.assertIn(token, self.smoke)

    def test_fetched_opened_separation_and_backend_gate(self):
        for token in ['__fetchedUrls', '__openedUrls', 'RUN_ATLAS_BACKEND_E2E']:
            self.assertIn(token, self.smoke)

    def test_no_destructive_actions_added(self):
        banned = ['approvePlan(', 'executePreview', 'applyPatch', 'bulk apply', 'bulk approve', 'auto apply', 'auto approve']
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
