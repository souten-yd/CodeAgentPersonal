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

    def test_local_storage_key_and_no_bulk(self):
        self.assertIn('atlas:lastRunId', self.ui)
        self.assertNotIn('bulk apply', self.ui.lower())
        self.assertNotIn('bulk approve', self.ui.lower())


if __name__ == '__main__':
    unittest.main()
