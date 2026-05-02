import unittest
from pathlib import Path


class TestPhase13PatchDashboardUIContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_dashboard_labels(self):
        self.assertIn('Atlas Run Dashboard', self.ui)
        self.assertIn('Load Atlas Dashboard', self.ui)
        self.assertIn('Open Atlas Dashboard', self.ui)

    def test_filters_and_attention_labels(self):
        for label in ['Pending', 'Approved', 'Approved Not Applied', 'Applied', 'Blocked', 'Verification Failed', 'Low Quality', 'Quality Not Evaluated', 'Missing Manual Check', 'Missing Telemetry', 'Reproposal Candidates', 'Patches with Telemetry', 'LLM Telemetry Records']:
            self.assertIn(label, self.ui)
        for label in ['Blocked patches', 'Low quality patches', 'Verification failed patches', 'Unreviewed patches', 'Missing telemetry patches', 'Missing manual check patches', 'Quality not evaluated patches', 'Reproposal candidates']:
            self.assertIn(label, self.ui)

    def test_no_bulk_controls(self):
        self.assertNotIn('bulk apply', self.ui.lower())
        self.assertNotIn('bulk approve', self.ui.lower())


if __name__ == '__main__':
    unittest.main()
