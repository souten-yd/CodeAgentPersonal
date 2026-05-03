import re
import unittest
from pathlib import Path


class TestPhase22_1AtlasStartButtonRegressionUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_start_atlas_workflow_is_async_safe(self):
        m = re.search(r'async function startAtlasWorkflow\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("setAtlasSubview('plan');", body)
        self.assertIn('renderAtlasPlanFlowSummary()', body)
        self.assertIn("startPlanWorkflow({ source: 'atlas', workspace: 'Atlas'", body)
        self.assertIn('catch (err)', body)
        self.assertIn('startAtlasWorkflow failed:', body)

    def test_start_atlas_buttons_use_start_atlas_workflow(self):
        for token in [
            '<button class="phase1-plan-btn" type="button" onclick="startAtlasWorkflow()">Start Atlas</button>',
            "addBtn('Start Atlas', startAtlasWorkflow, true);",
            "onclick=\"startAtlasWorkflow()\"",
        ]:
            self.assertIn(token, self.ui)

    def test_start_plan_workflow_silent_return_guarded_for_atlas(self):
        m = re.search(r'async function runGuidedPlanWorkflow\(options = \{\}\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("if (!text && source === 'atlas')", body)
        self.assertIn('Atlas Start needs a request.', body)
        self.assertIn("addMsg('system', msg);", body)
        self.assertIn("addLog('warn', 'atlas', msg);", body)

    def test_error_and_status_are_surfaced(self):
        for token in [
            "addMsg('system', 'Starting Atlas guided planning workflow...');",
            "addMsg('error', 'Atlas Start failed: '",
            "addLog('err', 'atlas', 'Start Atlas failed: '",
            '_updatePlanWorkflowState({ lastError: msg });',
        ]:
            self.assertIn(token, self.ui)

    def test_no_workflow_bypass_keywords(self):
        lower = self.ui.lower()
        for forbidden in ['bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(forbidden, lower)
        self.assertNotIn('/execute-preview', lower)

    def test_atlas_ui_remains(self):
        for token in ['id="atlas-panel-col"', 'id="atlas-workbench-card"', 'Atlas Workbench', 'Guided Plan Flow']:
            self.assertIn(token, self.ui)


if __name__ == '__main__':
    unittest.main()
