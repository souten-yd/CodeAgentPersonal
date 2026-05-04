import unittest
from pathlib import Path


class TestPhase31_0bAtlasChatDecouplingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')
        cls.smoke = Path('scripts/smoke_ui_modes_playwright.py').read_text(encoding='utf-8')
        cls.matrix = Path('scripts/run_debug_test_matrix.py').read_text(encoding='utf-8')

    def test_requirement_sync_and_chat_button_absent(self):
        self.assertNotIn('copyChatInputToAtlasRequirement', self.ui)
        self.assertNotIn('atlas-requirement-use-chat-btn', self.ui)
        self.assertIn('function deriveAtlasRequirementSource()', self.ui)
        self.assertNotIn("document.getElementById('input')", self.ui.split('function deriveAtlasRequirementSource()', 1)[1].split('function getAtlasRequirementText()', 1)[0])
        self.assertIn('function syncAtlasRequirementToChatInput(_text) {\n  return;\n}', self.ui)

    def test_atlas_workflow_no_chat_addmsg(self):
        atlas_block = self.ui.split('async function startAtlasWorkflow()', 1)[1].split('function startAgentGuidedWorkflow()', 1)[0]
        self.assertNotIn("addMsg('system'", atlas_block)
        self.assertNotIn("addMsg('error'", atlas_block)

    def test_smoke_uses_atlas_dom_and_non_mirroring_assert(self):
        self.assertIn('atlas-workbench-status', self.smoke)
        self.assertIn('atlas-requirement-status', self.smoke)
        self.assertIn('data-atlas-subview-panel', self.smoke)
        self.assertIn('new_messages = after_messages[len(before_messages):]', self.smoke)
        for token in ['Atlas Workflow Status', 'Requirement Preview', 'Boss']:
            self.assertIn(token, self.smoke)

    def test_no_destructive_automation_and_debug_safety(self):
        for token in ['approvePlan(', 'executePreview(', 'applyPatch(', 'auto approve', 'auto apply']:
            self.assertNotIn(token, self.smoke)
        for token in ['approve_plan', 'execute_preview', 'apply_patch']:
            self.assertNotIn(token, self.matrix)


if __name__ == '__main__':
    unittest.main()
