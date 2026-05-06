import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'main.py').read_text(encoding='utf-8')
MATRIX = (ROOT / 'scripts' / 'run_debug_test_matrix.py').read_text(encoding='utf-8')
SMOKE = (ROOT / 'scripts' / 'smoke_ui_modes_playwright.py').read_text(encoding='utf-8')

class TestPhase300DebugTestHarnessContract(unittest.TestCase):
    def test_debug_flag_exists(self):
        self.assertIn('KASANE_DEBUG_TEST_HARNESS', MAIN)

    def test_routes_exist(self):
        self.assertIn('/debug/tests', MAIN)
        self.assertIn('/api/debug/tests/run-all', MAIN)
        self.assertIn('/api/debug/tests/runs/{run_id}', MAIN)

    def test_run_all_continue_after_failures(self):
        self.assertIn('for preset in TEST_PRESETS', MATRIX)
        self.assertNotIn('break', MATRIX)

    def test_allowlist_presets(self):
        self.assertIn('TEST_PRESETS', MATRIX)
        self.assertIn('backend_preflight', MATRIX)
        self.assertIn('plan_approval_gate', MATRIX)
        self.assertIn('plan_approval_actionability', MATRIX)

    def test_no_arbitrary_command_execution(self):
        self.assertNotIn('shell=True', MATRIX)
        self.assertNotIn('command =', MATRIX)
        self.assertIn('subprocess.run(preset.command', MATRIX)

    def test_artifact_paths_exist(self):
        self.assertIn('debug_test_runs', MATRIX)
        self.assertIn('PLAYWRIGHT_SMOKE_ARTIFACT_DIR', MATRIX)
        self.assertIn('PLAYWRIGHT_SMOKE_ARTIFACT_DIR', SMOKE)
        self.assertIn('SMOKE_SCENARIOS', SMOKE)
        self.assertIn('--list-scenarios', SMOKE)

    def test_no_destructive_presets(self):
        self.assertNotIn('approve_plan', MATRIX)
        self.assertNotIn('execute_preview', MATRIX)
        self.assertNotIn('apply_patch', MATRIX)

    def test_default_can_be_disabled(self):
        self.assertIn('== "1"', MAIN)

if __name__ == '__main__':
    unittest.main()
