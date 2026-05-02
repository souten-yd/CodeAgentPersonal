import unittest
from pathlib import Path


class TestPhase17AtlasSubviewsUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_subview_tabs_exist(self):
        for label in ['Overview', 'Plan', 'Runs', 'Dashboard', 'Patch Review', 'Legacy']:
            self.assertIn(label, self.ui)

    def test_helper_and_data_attributes_exist(self):
        self.assertIn('function setAtlasSubview(name)', self.ui)
        self.assertIn('data-atlas-subview', self.ui)
        self.assertIn('data-atlas-subview-tab', self.ui)

    def test_default_overview_exists(self):
        self.assertIn('id="atlas-workbench-card" data-atlas-subview="overview"', self.ui)

    def test_existing_host_ids_remain(self):
        for host_id in [
            'atlas-workbench-card',
            'atlas-workbench-card-atlas-dashboard',
            'atlas-workbench-card-patch-list',
            'atlas-workbench-card-atlas-runs-list',
            'atlas-workbench-card-atlas-run-input',
            'atlas-workbench-card-atlas-last-run',
        ]:
            self.assertIn(host_id, self.ui)

    def test_actions_trigger_subview_transitions(self):
        for hook in [
            "setAtlasSubview('runs')",
            "setAtlasSubview('dashboard')",
            "setAtlasSubview('patch_review')",
            "setAtlasSubview('plan')",
        ]:
            self.assertIn(hook, self.ui)

    def test_legacy_compatibility_remains(self):
        self.assertIn('function openLegacyTaskFromAtlas()', self.ui)
        self.assertIn('Open Legacy Task', self.ui)
        self.assertIn('Open Agent Advanced', self.ui)

    def test_mobile_layout_safety(self):
        self.assertIn('.atlas-subview-tabs', self.ui)
        self.assertIn('flex-wrap:wrap', self.ui)

    def test_no_bulk_controls(self):
        lower = self.ui.lower()
        self.assertNotIn('bulk apply', lower)
        self.assertNotIn('bulk approve', lower)


if __name__ == '__main__':
    unittest.main()
