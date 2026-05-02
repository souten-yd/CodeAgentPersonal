import re
import unittest
from pathlib import Path


class TestPhase19AtlasGuidedPlanUxUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_guided_plan_flow_copy_exists(self):
        for token in [
            'Atlas Guided Plan Flow',
            'Requirement',
            'Plan',
            'Review',
            'Approval',
            'Execute Preview',
            'Patch Review',
        ]:
            self.assertIn(token, self.ui)

    def test_plan_flow_dom_ids_exist(self):
        self.assertIn('id="atlas-workbench-card-plan-flow"', self.ui)
        self.assertIn('id="atlas-workbench-card-plan-next-action"', self.ui)

    def test_render_helper_exists(self):
        self.assertIn('function renderAtlasPlanFlowSummary()', self.ui)

    def test_update_state_calls_plan_flow_render(self):
        m = re.search(r'function _updatePlanWorkflowState\(partial = \{\}\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        self.assertIn('renderAtlasPlanFlowSummary();', m.group(1))

    def test_render_reads_plan_workflow_state(self):
        m = re.search(r'function renderAtlasPlanFlowSummary\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('deriveAtlasPlanFlowState()', body)
        self.assertIn("document.getElementById('atlas-workbench-card-plan-flow')", body)
        self.assertIn("document.getElementById('atlas-workbench-card-plan-next-action')", body)


    def test_state_mapping_helpers_exist(self):
        self.assertIn('function atlasHasValue(v)', self.ui)
        self.assertIn('function deriveAtlasPlanFlowState()', self.ui)

    def test_render_uses_derived_state(self):
        m = re.search(r'function renderAtlasPlanFlowSummary\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('const flow = deriveAtlasPlanFlowState();', body)

    def test_derived_mapping_includes_alias_fields(self):
        for token in [
            'requirementResult',
            'requirementText',
            'planningResult',
            'generatedPlan',
            'planMarkdown',
            'planReview',
            'approvalStatus',
            'planApproved',
            'executionRunId',
            'previewRunId',
            'patchCount',
        ]:
            self.assertIn(token, self.ui)

    def test_next_action_strings_remain(self):
        for token in [
            'Start Atlas',
            'Review generated plan',
            'Approve plan',
            'Run Execute Preview',
            'Open Patch Review',
        ]:
            self.assertIn(token, self.ui)

    def test_render_avoids_inner_html(self):
        m = re.search(r'function renderAtlasPlanFlowSummary\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        self.assertNotIn('innerHTML', m.group(1))

    def test_start_atlas_still_selects_plan_and_uses_atlas_source(self):
        m = re.search(r'function startAtlasWorkflow\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("setAtlasSubview('plan');", body)
        self.assertIn("return startPlanWorkflow({ source: 'atlas', workspace: 'Atlas' });", body)

    def test_safety_copy_exists(self):
        for token in [
            'Execute Preview remains locked until plan approval',
            'No apply happens from this panel',
            'Patch application still requires Patch Review approval',
        ]:
            self.assertIn(token, self.ui)

    def test_navigation_buttons_exist(self):
        for token in [
            "onclick=\"setAtlasSubview('runs')\"",
            "onclick=\"setAtlasSubview('dashboard')\"",
            "onclick=\"setAtlasSubview('patch_review')\"",
            'Open Runs',
            'Open Dashboard',
            'Open Patch Review',
        ]:
            self.assertIn(token, self.ui)

    def test_no_destructive_automation(self):
        lower = self.ui.lower()
        self.assertNotIn('bulk apply', lower)
        self.assertNotIn('bulk approve', lower)
        self.assertNotIn('auto apply', lower)
        self.assertNotIn('auto approve', lower)


if __name__ == '__main__':
    unittest.main()
