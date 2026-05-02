import unittest
from pathlib import Path


class TestPhase14AtlasRunSelectorUIContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_labels(self):
        for label in [
            'Atlas Runs',
            'Load Recent Atlas Runs',
            'Open Run Dashboard',
            'Open Last Atlas Dashboard',
            'Open Patch Review for this run',
            'Refresh Atlas Dashboard',
        ]:
            self.assertIn(label, self.ui)

    def test_last_run_restore_and_prefill_contract(self):
        self.assertIn('atlas:lastRunId', self.ui)
        self.assertIn('atlas:lastDashboardRunId', self.ui)
        self.assertIn('lastRunId: getAtlasLastRunId()', self.ui)
        self.assertIn('function restoreAtlasLastRunState()', self.ui)
        self.assertIn('Last Run:', self.ui)
        self.assertIn('value="${esc(getAtlasLastRunId())}"', self.ui)
        self.assertIn('Open Last Atlas Dashboard', self.ui)
        self.assertIn('function ensureAtlasDashboardHost()', self.ui)

    def test_no_bulk_actions(self):
        self.assertNotIn('bulk apply', self.ui.lower())
        self.assertNotIn('bulk approve', self.ui.lower())


if __name__ == '__main__':
    unittest.main()
