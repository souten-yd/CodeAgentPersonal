import unittest
from pathlib import Path


class TestPhase155AtlasNavPolishUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_explicit_legacy_task_helper_exists(self):
        self.assertIn('function openLegacyTaskFromAtlas()', self.ui)

    def test_open_legacy_task_uses_explicit_helper(self):
        self.assertIn('onclick="openLegacyTaskFromAtlas();">Open Legacy Task</button>', self.ui)
        self.assertNotIn("onclick=\"setMode('chat');toggleChatTaskMode();\">Open Legacy Task</button>", self.ui)

    def test_open_task_panel_uses_explicit_helper(self):
        self.assertIn('onclick="openLegacyTaskFromAtlas();">Open Task Panel</button>', self.ui)

    def test_toggle_function_remains(self):
        self.assertIn('function toggleChatTaskMode()', self.ui)

    def test_atlas_workbench_note_exists(self):
        self.assertIn('Atlas Workbench', self.ui)
        self.assertTrue('run audit' in self.ui.lower() or 'patch review' in self.ui.lower())

    def test_agent_advanced_note_exists(self):
        self.assertIn('Agent is the advanced runtime surface. Atlas is the guided workflow for normal work.', self.ui)

    def test_mobile_atlas_remains(self):
        self.assertIn('id="mob-atlas"', self.ui)
        self.assertIn("const _ATLAS_MOB_TAB_IDS = ['mob-atlas'];", self.ui)
        self.assertIn("onclick=\"mobSwitch('atlas')\"", self.ui)

    def test_no_destructive_bulk_controls(self):
        lower = self.ui.lower()
        self.assertNotIn('bulk apply', lower)
        self.assertNotIn('bulk approve', lower)


if __name__ == '__main__':
    unittest.main()
