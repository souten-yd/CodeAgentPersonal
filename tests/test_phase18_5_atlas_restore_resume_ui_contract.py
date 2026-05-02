import re
import unittest
from pathlib import Path


class TestPhase18_5AtlasRestoreResumeUiContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_resume_notice_exists(self):
        self.assertIn('atlas-workbench-card-resume-notice', self.ui)
        self.assertIn('function updateAtlasResumeNotice(subview)', self.ui)

    def test_notice_uses_text_content(self):
        m = re.search(r'function updateAtlasResumeNotice\(subview\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn('notice.textContent =', body)
        self.assertNotIn('notice.innerHTML', body)

    def test_set_subview_updates_notice(self):
        m = re.search(r'function setAtlasSubview\(name\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        self.assertIn('updateAtlasResumeNotice(next);', m.group(1))

    def test_restore_updates_notice(self):
        m = re.search(r'function restoreAtlasSubviewState\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        self.assertIn('updateAtlasResumeNotice(subview);', m.group(1))

    def test_restore_still_no_auto_fetch(self):
        m = re.search(r'function restoreAtlasSubviewState\(\) \{([\s\S]*?)\n\}', self.ui)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertNotIn('loadAtlasRunDashboard', body)
        self.assertNotIn('loadPhase8Patches', body)
        self.assertNotIn('loadRecentAtlasRuns', body)

    def test_resume_copy_exists(self):
        for token in [
            'Resume Dashboard',
            'Open Last Atlas Dashboard',
            'Open Run Dashboard',
            'Resume Patch Review',
            'Open Patch Review for this run',
            'Recent runs are not auto-loaded after restore.',
            'Load Recent Atlas Runs',
            'data-atlas-last-run-mirror',
        ]:
            self.assertIn(token, self.ui)

    def test_no_bulk_controls(self):
        lower = self.ui.lower()
        self.assertNotIn('bulk apply', lower)
        self.assertNotIn('bulk approve', lower)


if __name__ == '__main__':
    unittest.main()
