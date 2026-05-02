import unittest
from pathlib import Path


class TestPhase12_8AgentGuidedWorkflowUIContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_guided_workflow_card_exists(self):
        self.assertIn('Guided Workflow', self.ui)
        self.assertIn('agent-guided-workflow-card', self.ui)
        self.assertIn('Start Guided Workflow', self.ui)

    def test_agent_entry_function_uses_shared_workflow(self):
        self.assertIn('function startAgentGuidedWorkflow()', self.ui)
        self.assertIn("return startPlanWorkflow({ source: 'agent_guided_workflow', workspace: 'Agent' });", self.ui)
        self.assertIn('agent_guided_workflow', self.ui)

    def test_start_plan_workflow_remains_compatible(self):
        self.assertIn('onclick="startPlanWorkflow()"', self.ui)
        self.assertIn('function startPlanWorkflow(options = {})', self.ui)
        self.assertIn('return runGuidedPlanWorkflow(options);', self.ui)

    def test_plan_workflow_state_has_source_workspace(self):
        self.assertIn('source:', self.ui)
        self.assertIn('workspace:', self.ui)
        self.assertIn('Source:', self.ui)
        self.assertIn('Workspace:', self.ui)

    def test_task_compatibility_note_exists(self):
        self.assertIn('Taskは今後Agent内のGuided Workflowへ統合予定です。既存互換のため当面は残します。', self.ui)


if __name__ == '__main__':
    unittest.main()
