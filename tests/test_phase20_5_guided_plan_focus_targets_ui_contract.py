import re
import unittest
from pathlib import Path


class TestPhase20_5GuidedPlanFocusTargetsUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_focus_helpers_exist(self):
        self.assertIn('function focusAtlasWorkflowSection(kind)', self.ui)
        self.assertIn('function findAtlasWorkflowTarget(kind)', self.ui)

    def test_focus_anchors_exist(self):
        for token in [
            'id="atlas-plan-review-anchor"',
            'id="atlas-plan-approval-anchor"',
            'id="atlas-plan-execute-preview-anchor"',
        ]:
            self.assertIn(token, self.ui)

    def test_highlight_class_exists(self):
        self.assertIn('.atlas-focus-highlight{', self.ui)

    def test_action_buttons_use_focus_helper(self):
        m = re.search(r'function renderAtlasPlanNextActionButtons\(flow\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("focusAtlasWorkflowSection('review')", body)
        self.assertIn("focusAtlasWorkflowSection('approval')", body)
        self.assertIn("focusAtlasWorkflowSection('execute_preview')", body)

    def test_patch_review_stays_safe(self):
        self.assertIn("addBtn('Open Patch Review', openPatchReviewFromWorkbench);", self.ui)

    def test_no_dangerous_direct_calls_in_focus_and_buttons(self):
        for fn in ['focusAtlasWorkflowSection', 'renderAtlasPlanNextActionButtons']:
            m = re.search(rf'function {fn}\([^)]*\) \{{([\s\S]*?)\n\}}', self.ui)
            self.assertIsNotNone(m)
            body = m.group(1).lower()
            self.assertNotIn('fetch(', body)
            self.assertNotIn('approveplan(', body)
            self.assertNotIn('executepreview', body)
            self.assertNotIn('bulk apply', body)
            self.assertNotIn('bulk approve', body)
            self.assertNotIn('auto apply', body)
            self.assertNotIn('auto approve', body)

    def test_safety_copy_and_show_panel_remain(self):
        self.assertIn('Approval and Patch Review gates remain required', self.ui)
        self.assertIn('showAtlasPanel()', self.ui)


if __name__ == '__main__':
    unittest.main()
