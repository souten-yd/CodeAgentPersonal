import unittest
from pathlib import Path


class TestPhase25418ReferenceCardSourceUrlFinalContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = Path("scripts/smoke_ui_modes_playwright.py").read_text(encoding="utf-8")

    def test_unconditional_source_url_assert_removed(self):
        self.assertNotIn(
            'source_url_button_state = await page.evaluate("""() => {',
            self.smoke,
        )
        self.assertNotIn(
            'if source_url_button_state.get("exists") and not source_url_button_state.get("disabled"):',
            self.smoke,
        )

    def test_source_url_diagnostic_statuses_exist(self):
        self.assertIn('source_url_action_status = "opened"', self.smoke)
        self.assertIn('clickedNoOpen', self.smoke)

    def test_disabled_or_missing_source_url_is_diagnostic_only(self):
        self.assertIn('source_url_action_status = "skippedDisabled"', self.smoke)
        self.assertIn('source_url_action_status = "skippedMissing"', self.smoke)
        self.assertIn('INFO: Source URL action skipped: button disabled', self.smoke)

    def test_no_force_click(self):
        self.assertNotIn('force=True', self.smoke)

    def test_full_text_highlight_download_checks_remain(self):
        for token in [
            '/nexus/sources/src-1/text',
            '/nexus/sources/src-1/chunks',
            '/nexus/sources/src-1/original',
            'source_id: src-1',
            'mode: text',
            'doc-1:0',
        ]:
            self.assertIn(token, self.smoke)

    def test_mock_url_fields_exist(self):
        for token in ['final_url', 'url', 'source_url', 'original_url', 'link']:
            self.assertIn(token, self.smoke)

    def test_backend_e2e_remains_opt_in(self):
        self.assertIn('RUN_ATLAS_BACKEND_E2E', self.smoke)

    def test_destructive_actions_not_added(self):
        banned = ['approvePlan(', 'executePreview', 'applyPatch', 'bulk apply', 'bulk approve', 'auto apply', 'auto approve']
        for token in banned:
            self.assertNotIn(token, self.smoke)


if __name__ == "__main__":
    unittest.main()
