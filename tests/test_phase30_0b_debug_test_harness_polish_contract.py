from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'main.py').read_text(encoding='utf-8')
MATRIX = (ROOT / 'scripts' / 'run_debug_test_matrix.py').read_text(encoding='utf-8')
DOCKER = (ROOT / 'Dockerfile').read_text(encoding='utf-8')


class Phase300bDebugHarnessPolishContract(unittest.TestCase):
    def test_docker_arg_redeclared_in_stages(self):
        self.assertIn('ARG KASANE_DEBUG_TEST_HARNESS=1', DOCKER)
        self.assertGreaterEqual(DOCKER.count('ARG KASANE_DEBUG_TEST_HARNESS=1'), 2)
        self.assertIn('ENV DEBIAN_FRONTEND=noninteractive', DOCKER)
        self.assertIn('KASANE_DEBUG_TEST_HARNESS=${KASANE_DEBUG_TEST_HARNESS}', DOCKER)

    def test_smoke_env_clear_exists(self):
        self.assertIn('SMOKE_ENV_KEYS', MATRIX)
        self.assertIn('env.pop(key, None)', MATRIX)
        self.assertIn('RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE', MATRIX)
        self.assertIn('PLAYWRIGHT_SMOKE_ARTIFACT_DIR', MATRIX)

    def test_incremental_result_writing_exists(self):
        self.assertIn('"current_test"', MATRIX)
        self.assertIn('"status": "running"', MATRIX)
        self.assertIn('_write_progress(run_dir, payload)', MATRIX)
        self.assertIn('summary.md', MATRIX)

    def test_html_escape_exists(self):
        self.assertIn('import html', MAIN)
        self.assertIn('html.escape', MAIN)

    def test_run_all_browser_redirect_or_html_link_exists(self):
        self.assertTrue('RedirectResponse' in MAIN or 'view_url' in MAIN)

    def test_safety_remains(self):
        self.assertNotIn('shell=True', MATRIX)
        self.assertNotIn('approve_plan', MATRIX)
        self.assertNotIn('execute_preview', MATRIX)
        self.assertNotIn('apply_patch', MATRIX)


if __name__ == '__main__':
    unittest.main()
