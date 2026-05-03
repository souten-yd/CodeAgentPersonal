import re
import unittest
from pathlib import Path


class TestPhase21_5DynamicWorkflowTargetsUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_dynamic_workflow_targets_exist(self):
        for token in [
            'data-atlas-workflow-target="dynamic-plan-review"',
            'data-atlas-workflow-target="dynamic-approval"',
            'data-atlas-workflow-target="dynamic-execute-preview"',
            'data-atlas-workflow-target="dynamic-patch-review"',
        ]:
            self.assertIn(token, self.ui)

    def test_find_target_prioritizes_dynamic_targets(self):
        m = re.search(r'function findAtlasWorkflowTarget\(kind\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertLess(body.index('[data-atlas-workflow-target="dynamic-plan-review"]'), body.index('[data-atlas-workflow-target="plan-review"]'))
        self.assertLess(body.index('[data-atlas-workflow-target="dynamic-approval"]'), body.index('[data-atlas-workflow-target="approval"]'))
        self.assertLess(body.index('[data-atlas-workflow-target="dynamic-execute-preview"]'), body.index('[data-atlas-workflow-target="execute-preview"]'))
        self.assertLess(body.index('[data-atlas-workflow-target="dynamic-patch-review"]'), body.index('[data-atlas-workflow-target="patch-review"]'))

    def test_stable_fallback_targets_remain(self):
        for token in [
            '[data-atlas-workflow-target="plan-review"]',
            '[data-atlas-workflow-target="approval"]',
            '[data-atlas-workflow-target="execute-preview"]',
            '[data-atlas-workflow-target="patch-review"]',
        ]:
            self.assertIn(token, self.ui)

    def test_lightweight_anchors_remain(self):
        for token in [
            'id="atlas-plan-review-anchor"',
            'id="atlas-plan-approval-anchor"',
            'id="atlas-plan-execute-preview-anchor"',
        ]:
            self.assertIn(token, self.ui)

    def test_focus_helper_remains_non_destructive(self):
        m = re.search(r'function focusAtlasWorkflowSection\(kind\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('scrollIntoView', body)
        self.assertIn('atlas-focus-highlight', body)
        lower = body.lower()
        for token in [
            'fetch(',
            'approveplan(',
            'executepreview',
            'applypatch',
            'bulk apply',
            'bulk approve',
            'auto apply',
            'auto approve',
        ]:
            self.assertNotIn(token, lower)

    def test_action_buttons_still_use_focus_helper(self):
        m = re.search(r'function renderAtlasPlanNextActionButtons\(flow\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("focusAtlasWorkflowSection('review')", body)
        self.assertIn("focusAtlasWorkflowSection('approval')", body)
        self.assertIn("focusAtlasWorkflowSection('execute_preview')", body)


if __name__ == '__main__':
    unittest.main()
