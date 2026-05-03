import re
import unittest
from pathlib import Path


class TestPhase23_5AtlasRequirementInputPolishUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_persistence_key_exists(self):
        self.assertIn("const ATLAS_REQUIREMENT_INPUT_KEY = 'atlas:requirementInput';", self.ui)

    def test_helpers_exist(self):
        for token in [
            'function persistAtlasRequirementInput()',
            'function restoreAtlasRequirementInput()',
            'function clearAtlasRequirementInput()',
            'function copyChatInputToAtlasRequirement()',
            'function updateAtlasRequirementCharCount()',
        ]:
            self.assertIn(token, self.ui)

    def test_ui_controls_exist(self):
        for token in [
            'id="atlas-requirement-clear-btn"',
            'id="atlas-requirement-use-chat-btn"',
            'id="atlas-requirement-char-count"',
        ]:
            self.assertIn(token, self.ui)

    def test_input_saves_on_change(self):
        self.assertIn("addEventListener('input'", self.ui)

    def test_clear_does_not_clear_chat_input(self):
        m = re.search(r'function clearAtlasRequirementInput\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        self.assertNotIn("document.getElementById('input').value = ''", m.group(1))

    def test_restore_is_called(self):
        m = re.search(r'function restoreAtlasSubviewState\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        self.assertIn('restoreAtlasRequirementInput();', m.group(1))

    def test_status_strings_exist(self):
        for token in [
            'Requirement draft saved.',
            'Requirement draft restored.',
            'Requirement cleared.',
            'Copied from Chat input.',
            'Chat input is empty.',
        ]:
            self.assertIn(token, self.ui)

    def test_no_destructive_workflow_changes(self):
        lower = self.ui.lower()
        for forbidden in ['bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(forbidden, lower)
        self.assertNotIn('/execute-preview', lower)


if __name__ == '__main__':
    unittest.main()
