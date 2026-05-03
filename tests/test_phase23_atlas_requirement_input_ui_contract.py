import re
import unittest
from pathlib import Path


class TestPhase23AtlasRequirementInputUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_requirement_input_exists(self):
        self.assertIn('id="atlas-requirement-input"', self.ui)
        self.assertIn('<textarea id="atlas-requirement-input"', self.ui)
        self.assertIn('Describe the task, requirement, bug, or change you want Atlas to plan…', self.ui)
        self.assertIn('id="atlas-requirement-status"', self.ui)

    def test_helpers_exist(self):
        self.assertIn('function getAtlasRequirementText()', self.ui)
        self.assertIn('function syncAtlasRequirementToChatInput(text)', self.ui)

    def test_atlas_input_priority(self):
        m = re.search(r'function getAtlasRequirementText\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertTrue(
            "document.getElementById('atlas-requirement-input')" in body
            or 'deriveAtlasRequirementSource().text' in body
        )

    def test_start_atlas_uses_requirement_input(self):
        m = re.search(r'async function startAtlasWorkflow\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertTrue('getAtlasRequirementText()' in body or 'deriveAtlasRequirementSource()' in body)
        self.assertIn('syncAtlasRequirementToChatInput(requirementText);', body)
        self.assertIn("startPlanWorkflow({ source: 'atlas', workspace: 'Atlas', requirementText", body)

    def test_generate_plan_only_from_input_is_legacy_safe(self):
        m = re.search(r'async function generatePlanOnlyFromInput\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("document.getElementById('input')", body)
        self.assertNotIn('options?.requirementText', body)
        self.assertNotIn("source === 'atlas'", body)
        self.assertNotIn('getAtlasRequirementText()', body)
        self.assertNotIn('syncAtlasRequirementToChatInput', body)

    def test_run_guided_plan_workflow_supports_requirement_text(self):
        m = re.search(r'async function runGuidedPlanWorkflow\(options = \{\}\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('options?.requirementText', body)
        self.assertTrue("source === 'atlas' ? getAtlasRequirementText()" in body or 'deriveAtlasRequirementSource()' in body)
        self.assertIn('syncAtlasRequirementToChatInput(requirementText);', body)
        self.assertIn('return generatePlanOnlyFromInput();', body)

    def test_empty_request_feedback_remains(self):
        self.assertIn('Atlas Start needs a request.', self.ui)

    def test_no_destructive_workflow_changes(self):
        lower = self.ui.lower()
        for forbidden in ['bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(forbidden, lower)
        self.assertNotIn('/execute-preview', lower)

    def test_existing_atlas_ui_remains(self):
        for token in ['Atlas Workbench', 'Guided Plan Flow', 'Start Atlas']:
            self.assertIn(token, self.ui)


if __name__ == '__main__':
    unittest.main()
