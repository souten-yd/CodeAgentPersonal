import unittest
from pathlib import Path


class TestPhase12_8AgentGuidedWorkflowUIContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_atlas_card_exists(self):
        self.assertIn('Atlas', self.ui)
        self.assertIn('agent-guided-workflow-card', self.ui)
        self.assertIn('Start Atlas', self.ui)

    def test_agent_entry_function_is_backward_compatible_alias(self):
        self.assertIn('function startAtlasWorkflow()', self.ui)
        self.assertIn("return startPlanWorkflow({ source: 'atlas', workspace: 'Atlas' });", self.ui)
        self.assertIn('function startAgentGuidedWorkflow()', self.ui)
        self.assertIn('return startAtlasWorkflow();', self.ui)

    def test_start_plan_workflow_remains_compatible(self):
        self.assertIn('onclick="startPlanWorkflow()"', self.ui)
        self.assertIn('function startPlanWorkflow(options = {})', self.ui)
        self.assertIn('return runGuidedPlanWorkflow(options);', self.ui)

    def test_plan_workflow_state_has_source_workspace(self):
        self.assertIn("source: 'atlas'", self.ui)
        self.assertIn("workspace: 'Atlas'", self.ui)
        self.assertIn('Source:', self.ui)
        self.assertIn('Workspace:', self.ui)

    def test_task_compatibility_note_exists(self):
        self.assertIn('Taskは互換のため残します。新しいGuided WorkflowはAtlasとして扱います。', self.ui)


if __name__ == '__main__':
    unittest.main()
