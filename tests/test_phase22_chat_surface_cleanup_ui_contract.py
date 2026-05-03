from __future__ import annotations

import re
import unittest
from pathlib import Path


class Phase22ChatSurfaceCleanupUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_chat_role_copy_exists(self):
        self.assertIn('Chat is for lightweight conversation, Q&amp;A, and quick investigation.', self.ui)
        self.assertIn('Use Atlas for guided work planning, approval, execution preview, and patch review.', self.ui)

    def test_atlas_legacy_compatibility_copy_and_actions_exist(self):
        self.assertIn('Open Legacy Task', self.ui)
        self.assertIn('Open Agent Advanced', self.ui)
        self.assertIn('Task remains compatibility path under Atlas Legacy.', self.ui)
        self.assertIn('Agent remains advanced runtime surface.', self.ui)

    def test_open_legacy_task_flow_remains_explicit(self):
        self.assertIn('function openLegacyTaskFromAtlas()', self.ui)
        body = self.ui.split('function openLegacyTaskFromAtlas()', 1)[1].split('function toggleChatTaskMode()', 1)[0]
        self.assertIn("setMode('chat');", body)
        self.assertIn("window.setChatTaskMode('task');", body)
        self.assertNotIn("setMode('chat');toggleChatTaskMode();", self.ui)

    def test_agent_remains_available(self):
        for token in [
            'id="btn-agent"',
            'id="agent-col"',
            'id="agent-panel-col"',
            'Agent is the advanced runtime surface. Atlas is the guided workflow for normal work.',
        ]:
            self.assertIn(token, self.ui)

    def test_atlas_remains_primary_guided_workflow_surface(self):
        for token in ['id="btn-atlas"', 'id="atlas-panel-col"', 'Atlas Workbench', 'Start Atlas']:
            self.assertIn(token, self.ui)

    def test_chat_copy_does_not_promote_task_or_agent_as_primary(self):
        segment = re.search(r'<div class="chat-role-note"[\s\S]*?</div>', self.ui)
        self.assertIsNotNone(segment)
        text = segment.group(0)
        self.assertIn('Use Atlas for guided work planning', text)
        self.assertNotIn('Use Task', text)
        self.assertNotIn('Use Agent', text)

    def test_no_destructive_automation_keywords(self):
        lowered = self.ui.lower()
        for forbidden in ['bulk apply', 'bulk approve', 'auto apply', 'auto approve']:
            self.assertNotIn(forbidden, lowered)


if __name__ == '__main__':
    unittest.main()
