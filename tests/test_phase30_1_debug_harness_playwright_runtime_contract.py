import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKER = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
DOCKERIGNORE = (ROOT / '.dockerignore').read_text(encoding='utf-8')
README = (ROOT / 'README.md').read_text(encoding='utf-8')
MATRIX = (ROOT / 'scripts' / 'run_debug_test_matrix.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'main.py').read_text(encoding='utf-8')


class Phase301DebugHarnessPlaywrightRuntimeContract(unittest.TestCase):
    def test_dockerfile_installs_playwright_for_debug_harness(self):
        self.assertIn('KASANE_DEBUG_TEST_HARNESS', DOCKER)
        self.assertIn('pip install --no-cache-dir playwright', DOCKER)
        self.assertIn('playwright install --with-deps chromium', DOCKER)

    def test_docs_state_chrome_extension_not_required(self):
        self.assertIn('Playwright + Chromium', README)
        self.assertIn('Chrome extension は不要', README)

    def test_skip_is_not_marked_passed(self):
        self.assertIn('SKIP: playwright is not installed', MATRIX)
        self.assertIn('"SKIP:"', MATRIX)
        self.assertIn('status = "skipped"', MATRIX)
        self.assertIn('finished_with_skips', MATRIX)

    def test_summary_includes_skipped_count(self):
        self.assertIn("payload.get('skipped', 0)", MATRIX)
        self.assertIn('skip:', MAIN)

    def test_workflow_file_included_for_static_contracts(self):
        self.assertIn('!.github/workflows/playwright-ui-smoke.yml', DOCKERIGNORE)

    def test_safety_remains(self):
        self.assertNotIn('shell=True', MATRIX)
        self.assertNotIn('approve_plan', MATRIX)
        self.assertNotIn('execute_preview', MATRIX)
        self.assertNotIn('apply_patch', MATRIX)


if __name__ == '__main__':
    unittest.main()
