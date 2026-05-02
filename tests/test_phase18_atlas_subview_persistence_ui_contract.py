import re
import unittest
from pathlib import Path


class TestPhase18AtlasSubviewPersistenceUIContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_localstorage_key_exists(self):
        self.assertIn('const ATLAS_LAST_SUBVIEW_KEY = \'atlas:lastSubview\';', self.ui)

    def test_subview_normalization_exists(self):
        self.assertIn("const ATLAS_SUBVIEWS = ['overview', 'plan', 'runs', 'dashboard', 'patch_review', 'legacy'];", self.ui)
        self.assertIn('function normalizeAtlasSubview(name)', self.ui)
        self.assertIn("return ATLAS_SUBVIEWS.includes(name) ? name : 'overview';", self.ui)

    def test_set_atlas_subview_persists(self):
        self.assertIn('function setAtlasSubview(name)', self.ui)
        self.assertIn('_atlasLsSet(ATLAS_LAST_SUBVIEW_KEY, next);', self.ui)

    def test_restore_helpers_exist(self):
        self.assertIn('function getAtlasLastSubview()', self.ui)
        self.assertIn('function restoreAtlasSubviewState()', self.ui)
        self.assertIn('setAtlasSubview(subview);', self.ui)
        self.assertIn('ensureAtlasWorkbenchHost();', self.ui)

    def test_setmode_and_mobile_restore(self):
        self.assertIn("} else if (m === 'atlas') {", self.ui)
        self.assertIn('restoreAtlasSubviewState();', self.ui)
        self.assertIn("} else if (name === 'atlas') {", self.ui)

    def test_restore_does_not_auto_fetch_dashboard_or_patch_or_runs(self):
        m = re.search(r'function restoreAtlasSubviewState\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertNotIn('loadAtlasRunDashboard', body)
        self.assertNotIn('loadPhase8Patches', body)
        self.assertNotIn('loadRecentAtlasRuns', body)

    def test_last_run_mirror_and_hosts_remain(self):
        for token in [
            'data-atlas-last-run-mirror',
            'atlas-workbench-card-atlas-last-run',
            'atlas-workbench-card-atlas-run-input',
            'atlas-workbench-card',
            'atlas-workbench-card-atlas-dashboard',
            'atlas-workbench-card-patch-list',
            'atlas-workbench-card-atlas-runs-list',
        ]:
            self.assertIn(token, self.ui)

    def test_no_bulk_controls(self):
        lower = self.ui.lower()
        self.assertNotIn('bulk apply', lower)
        self.assertNotIn('bulk approve', lower)


if __name__ == '__main__':
    unittest.main()
