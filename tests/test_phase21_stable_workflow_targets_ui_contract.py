import re
import unittest
from pathlib import Path


class TestPhase21StableWorkflowTargetsUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_workflow_target_attrs_exist(self):
        for token in [
            'data-atlas-workflow-target="plan-review"',
            'data-atlas-workflow-target="approval"',
            'data-atlas-workflow-target="execute-preview"',
            'data-atlas-workflow-target="patch-review"',
        ]:
            self.assertIn(token, self.ui)

    def test_find_target_prioritizes_workflow_targets(self):
        m = re.search(r'function findAtlasWorkflowTarget\(kind\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        for token in [
            '[data-atlas-workflow-target="plan-review"]',
            '[data-atlas-workflow-target="approval"]',
            '[data-atlas-workflow-target="execute-preview"]',
            '[data-atlas-workflow-target="patch-review"]',
        ]:
            self.assertIn(token, body)

    def test_fallback_anchors_remain(self):
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

    def test_no_dangerous_calls_in_focus_helper(self):
        m = re.search(r'function focusAtlasWorkflowSection\(kind\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1).lower()
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
            self.assertNotIn(token, body)

    def test_action_buttons_still_use_focus_helper(self):
        m = re.search(r'function renderAtlasPlanNextActionButtons\(flow\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("focusAtlasWorkflowSection('review')", body)
        self.assertIn("focusAtlasWorkflowSection('approval')", body)
        self.assertIn("focusAtlasWorkflowSection('execute_preview')", body)

    def test_patch_review_remains_safe(self):
        self.assertIn("addBtn('Open Patch Review', openPatchReviewFromWorkbench);", self.ui)


if __name__ == '__main__':
    unittest.main()
