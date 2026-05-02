import re
import unittest
from pathlib import Path


class TestPhase20GuidedPlanActionButtonsUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_next_action_buttons_dom_exists(self):
        self.assertIn('id="atlas-workbench-card-plan-next-action-buttons"', self.ui)

    def test_render_button_helper_exists(self):
        self.assertIn('function renderAtlasPlanNextActionButtons(flow)', self.ui)

    def test_render_summary_calls_button_renderer(self):
        m = re.search(r'function renderAtlasPlanFlowSummary\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        self.assertIn('renderAtlasPlanNextActionButtons(flow);', m.group(1))

    def test_button_labels_exist(self):
        for token in [
            'Start Atlas',
            'Open Atlas Panel',
            'Open Approval Panel',
            'Open Execute Preview',
            'Open Patch Review',
        ]:
            self.assertIn(token, self.ui)

    def test_safe_function_usage(self):
        for token in [
            'startAtlasWorkflow',
            'showAtlasPanel',
            'openPatchReviewFromWorkbench',
        ]:
            self.assertIn(token, self.ui)

    def test_no_direct_dangerous_calls(self):
        m = re.search(r'function renderAtlasPlanNextActionButtons\(flow\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1).lower()
        self.assertNotIn('fetch(', body)
        self.assertNotIn('bulk apply', body)
        self.assertNotIn('bulk approve', body)
        self.assertNotIn('auto apply', body)
        self.assertNotIn('auto approve', body)

    def test_safety_copy_exists(self):
        self.assertIn('Approval and Patch Review gates remain required', self.ui)

    def test_no_inner_html_in_render_helpers(self):
        for fn in ['renderAtlasPlanFlowSummary', 'renderAtlasPlanNextActionButtons']:
            m = re.search(rf'function {fn}\([^)]*\) \{{([\s\S]*?)\n\}}', self.ui)
            self.assertIsNotNone(m)
            self.assertNotIn('innerHTML', m.group(1))


if __name__ == '__main__':
    unittest.main()
