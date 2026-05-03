import re
import unittest
from pathlib import Path


class TestPhase24AtlasRequirementSourceStatusUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_source_helper_exists(self):
        self.assertIn('function deriveAtlasRequirementSource()', self.ui)

    def test_source_helper_tokens_exist(self):
        m = re.search(r'function deriveAtlasRequirementSource\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("source: 'atlas'", body)
        self.assertIn("source: 'chat'", body)
        self.assertIn("source: 'empty'", body)

    def test_get_requirement_text_priority_preserved(self):
        self.assertIn('function getAtlasRequirementText()', self.ui)
        self.assertIn('return deriveAtlasRequirementSource().text;', self.ui)

    def test_start_atlas_passes_requirement_source(self):
        m = re.search(r'async function startAtlasWorkflow\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('deriveAtlasRequirementSource()', body)
        self.assertIn("requirementSource: derived.source", body)

    def test_status_strings_exist(self):
        for token in [
            'Using Atlas requirement input.',
            'Falling back to Chat input.',
            'Enter a requirement to start.',
            'Starting Atlas guided planning workflow...',
            'Atlas Start failed.',
        ]:
            self.assertIn(token, self.ui)

    def test_run_guided_plan_workflow_source_aware(self):
        m = re.search(r'async function runGuidedPlanWorkflow\(options = \{\}\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('options?.requirementSource', body)
        self.assertIn('deriveAtlasRequirementSource()', body)
        self.assertIn('syncAtlasRequirementToChatInput(requirementText);', body)

    def test_generate_plan_only_from_input_legacy_safe(self):
        m = re.search(r'async function generatePlanOnlyFromInput\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertNotIn('options?.requirementText', body)
        self.assertNotIn("source === 'atlas'", body)
        self.assertNotIn('deriveAtlasRequirementSource', body)
        self.assertNotIn('getAtlasRequirementText', body)

    def test_no_destructive_workflow_changes(self):
        lower = self.ui.lower()
        for forbidden in ['bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(forbidden, lower)
        self.assertNotIn('/execute-preview', lower)


if __name__ == '__main__':
    unittest.main()
