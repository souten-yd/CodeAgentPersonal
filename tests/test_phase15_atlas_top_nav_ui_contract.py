import unittest
from pathlib import Path


class TestPhase15AtlasTopNavUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')
        cls.doc = Path('docs/agent_guided_workflow_integration.md').read_text(encoding='utf-8')

    def test_top_nav_has_atlas_mode(self):
        self.assertIn("id=\"btn-atlas\"", self.ui)
        self.assertIn("setMode('atlas')", self.ui)
        self.assertIn("['chat','atlas','agent','echo','nexus']", self.ui)

    def test_atlas_panel_actions_exist(self):
        for label in [
            'Start Atlas',
            'Open Atlas Panel',
            'Open Last Atlas Dashboard',
            'Load Recent Atlas Runs',
            'Open Run Dashboard',
            'Atlas Runs',
            'Atlas Workflow Status',
        ]:
            self.assertIn(label, self.ui)

    def test_task_and_agent_compatibility_remain(self):
        self.assertIn('Taskは互換のため残します。', self.ui)
        self.assertIn('Open Legacy Task', self.ui)
        self.assertIn('Agent powers Atlas workflows', self.ui)
        self.assertIn('Agent', self.ui)
        self.assertIn('mob-agent-chat', self.ui)
        self.assertIn('mob-agent-tasks', self.ui)

    def test_mobile_atlas_tab_exists(self):
        self.assertIn('id="mob-atlas"', self.ui)
        self.assertIn("onclick=\"mobSwitch('atlas')\"", self.ui)
        self.assertIn("const _ATLAS_MOB_TAB_IDS = ['mob-atlas'];", self.ui)

    def test_no_bulk_controls(self):
        lower = self.ui.lower()
        self.assertNotIn('bulk apply', lower)
        self.assertNotIn('bulk approve', lower)

    def test_docs_updated_for_phase15(self):
        self.assertIn('Chat / Atlas / Agent / Echo / Nexus', self.doc)
        self.assertIn('Task remains reachable from Atlas as Legacy/Guided Task', self.doc)
        self.assertIn('Future target remains: Chat / Atlas / Echo / Nexus', self.doc)


if __name__ == '__main__':
    unittest.main()
