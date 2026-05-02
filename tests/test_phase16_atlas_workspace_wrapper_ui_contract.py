import unittest
from pathlib import Path


class TestPhase16AtlasWorkspaceWrapperUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_atlas_wrapper_exists(self):
        self.assertIn('id="atlas-panel-col"', self.ui)
        self.assertIn('Atlas Workbench', self.ui)

    def test_atlas_wrapper_layout_safety(self):
        self.assertIn('.atlas-panel-col{overflow:auto;min-height:0}', self.ui)
        self.assertIn('flex-wrap:wrap', self.ui)
        self.assertIn('atlas-workbench-card-atlas-run-input', self.ui)
        self.assertTrue('min-width:0' in self.ui or 'max-width:100%' in self.ui)

    def test_atlas_wrapper_has_core_actions(self):
        for label in [
            'Start Atlas',
            'Open Last Atlas Dashboard',
            'Load Recent Atlas Runs',
            'Open Run Dashboard',
            'Open Legacy Task',
            'Open Agent Advanced',
        ]:
            self.assertIn(label, self.ui)

    def test_atlas_wrapper_reusable_hosts_exist(self):
        for host_id in [
            'atlas-workbench-card',
            'atlas-workbench-card-atlas-dashboard',
            'atlas-workbench-card-patch-list',
            'atlas-workbench-card-atlas-runs-list',
            'atlas-workbench-card-atlas-run-input',
        ]:
            self.assertIn(host_id, self.ui)

    def test_setmode_atlas_uses_wrapper(self):
        self.assertIn("} else if (m === 'atlas') {", self.ui)
        self.assertIn('ensureAtlasWorkbenchHost();', self.ui)

    def test_mobile_atlas_uses_wrapper(self):
        self.assertIn("const _ATLAS_MOB_TAB_IDS = ['mob-atlas'];", self.ui)
        self.assertIn("atc?.classList.remove('mob-hidden');", self.ui)
        self.assertIn("ensureAtlasWorkbenchHost();", self.ui)

    def test_mode_branches_hide_atlas_when_not_atlas(self):
        self.assertIn("if (atlasPanelCol) atlasPanelCol.style.display = 'none';", self.ui)

    def test_helper_functions_exist(self):
        for fn in [
            'function openLastAtlasDashboardFromWorkbench()',
            'function openManualAtlasRunDashboardFromWorkbench()',
            'function loadRecentAtlasRunsFromWorkbench()',
            'function openPatchReviewFromWorkbench()',
        ]:
            self.assertIn(fn, self.ui)

    def test_agent_compatibility_remains(self):
        self.assertIn('id="btn-agent"', self.ui)
        self.assertIn('id="mob-agent-chat"', self.ui)
        self.assertIn('id="mob-agent-tasks"', self.ui)

    def test_legacy_task_compatibility_remains(self):
        self.assertIn('function openLegacyTaskFromAtlas()', self.ui)
        self.assertIn('Open Legacy Task', self.ui)
        self.assertIn('function toggleChatTaskMode()', self.ui)

    def test_no_bulk_controls(self):
        lower = self.ui.lower()
        self.assertNotIn('bulk apply', lower)
        self.assertNotIn('bulk approve', lower)


if __name__ == '__main__':
    unittest.main()
