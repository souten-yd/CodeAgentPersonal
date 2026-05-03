import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = (ROOT / 'scripts' / 'run_debug_test_matrix.py').read_text(encoding='utf-8')
MAIN = (ROOT / 'main.py').read_text(encoding='utf-8')


class Phase301bDebugHarnessTimeoutStatusContract(unittest.TestCase):
    def test_timeout_count_exists(self):
        self.assertIn('"timeout": 0', MATRIX)
        self.assertIn('status = "timeout"', MATRIX)

    def test_final_status_does_not_pass_when_timeout_exists(self):
        self.assertIn('if failed > 0 or timeout > 0:', MATRIX)
        self.assertIn('payload["status"] = "finished_with_failures"', MATRIX)

    def test_skipped_remains_separate_from_passed(self):
        self.assertIn('status = "skipped"', MATRIX)
        self.assertIn('finished_with_skips', MATRIX)

    def test_summary_includes_timeout_count(self):
        self.assertIn("timeout: {payload.get('timeout', 0)}", MATRIX)
        self.assertIn("skip: {payload.get('skipped', 0)}", MATRIX)
        self.assertIn('skip:', MAIN)

    def test_safety_remains(self):
        self.assertNotIn('shell=True', MATRIX)
        self.assertNotIn('approve_plan', MATRIX)
        self.assertNotIn('execute_preview', MATRIX)
        self.assertNotIn('apply_patch', MATRIX)


if __name__ == '__main__':
    unittest.main()
