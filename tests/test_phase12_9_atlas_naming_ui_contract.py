import unittest
from pathlib import Path


class TestPhase12_9AtlasNamingUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')
        cls.doc = Path('docs/agent_guided_workflow_integration.md').read_text(encoding='utf-8')

    def test_atlas_label_and_start_button_exist(self):
        self.assertIn('Atlas', self.ui)
        self.assertIn('Start Atlas', self.ui)
        self.assertIn('Open Atlas Panel', self.ui)

    def test_atlas_entry_and_aliases_exist(self):
        self.assertIn('function startAtlasWorkflow()', self.ui)
        self.assertIn("return startPlanWorkflow({ source: 'atlas', workspace: 'Atlas' });", self.ui)
        self.assertIn('function startAgentGuidedWorkflow()', self.ui)
        self.assertIn('return startAtlasWorkflow();', self.ui)
        self.assertIn('function showAtlasPanel()', self.ui)
        self.assertIn('return showPlanWorkflowPanel();', self.ui)

    def test_status_panel_and_defaults_are_atlas(self):
        self.assertIn('Atlas Workflow Status', self.ui)
        self.assertIn("source: 'atlas'", self.ui)
        self.assertIn("workspace: 'Atlas'", self.ui)
        self.assertIn('Source:', self.ui)
        self.assertIn('Workspace:', self.ui)

    def test_backward_compatibility_kept(self):
        self.assertIn('function startPlanWorkflow(options = {})', self.ui)
        self.assertIn('onclick="startPlanWorkflow()"', self.ui)
        self.assertIn('Taskは互換のため残します。新しいGuided WorkflowはAtlasとして扱います。', self.ui)

    def test_docs_include_final_navigation_and_mapping(self):
        self.assertIn('Final target navigation', self.doc)
        self.assertIn('Chat', self.doc)
        self.assertIn('Atlas', self.doc)
        self.assertIn('Echo', self.doc)
        self.assertIn('Nexus', self.doc)
        self.assertIn('Agent runtime powers Atlas', self.doc)
        self.assertIn('Task remains for compatibility', self.doc)


if __name__ == '__main__':
    unittest.main()
