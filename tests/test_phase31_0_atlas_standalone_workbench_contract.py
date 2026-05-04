import unittest
from pathlib import Path


class TestPhase310AtlasStandaloneWorkbenchContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')
        cls.doc = Path('docs/agent_guided_workflow_integration.md').read_text(encoding='utf-8')
        cls.smoke = Path('scripts/smoke_ui_modes_playwright.py').read_text(encoding='utf-8')

    def test_chat_decoupling_language_exists(self):
        self.assertIn('Atlas is source of truth', self.ui)
        self.assertNotIn('Open in Atlas', self.ui)
        self.assertNotIn('Use Chat Input', self.ui)
        self.assertNotIn('copyChatInputToAtlasRequirement', self.ui)

    def test_atlas_scroll_css_exists(self):
        for token in ['min-height:0', 'overflow-y:auto', '100dvh', '-webkit-overflow-scrolling:touch']:
            self.assertIn(token, self.ui)

    def test_dashboard_workbench_terms_exist(self):
        for token in ['Workflow Workbench', 'Current Action', 'Requirement', 'Plan', 'Review', 'Approval', 'Agent Execution', 'Execute Preview', 'Patch Review']:
            self.assertIn(token, self.ui)

    def test_plan_belongs_to_atlas(self):
        self.assertIn("deriveAtlasRequirementSource", self.ui)
        self.assertNotIn("source: 'chat'", self.ui)

    def test_agent_migration_note_exists(self):
        self.assertIn('Agent will be moved under Atlas in Phase 31.1', self.doc)
        self.assertIn('Agent becomes the execution engine/work area inside Atlas', self.doc)

    def test_destructive_actions_not_automated(self):
        for token in ['approvePlan(', 'executePreview(', 'applyPatch(', 'auto approve', 'auto apply']:
            self.assertNotIn(token, self.smoke)

    def test_debug_harness_safety_remains(self):
        matrix = Path('scripts/run_debug_test_matrix.py').read_text(encoding='utf-8')
        for token in ['approve_plan', 'execute_preview', 'apply_patch']:
            self.assertNotIn(token, matrix)


if __name__ == '__main__':
    unittest.main()
