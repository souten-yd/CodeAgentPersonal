import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE = (ROOT / 'scripts' / 'smoke_ui_modes_playwright.py').read_text(encoding='utf-8')
MATRIX = (ROOT / 'scripts' / 'run_debug_test_matrix.py').read_text(encoding='utf-8')


class Phase304PlaywrightArtifactPathAndSkipContract(unittest.TestCase):
    def test_safe_artifact_path_helper_exists(self):
        self.assertIn('def safe_artifact_path(path: Path) -> str:', SMOKE)
        self.assertIn('relative_to', SMOKE)
        self.assertIn('except ValueError', SMOKE)
        self.assertIn('return str(resolved_path)', SMOKE)

    def test_smoke_script_avoids_unsafe_relative_to_root_append(self):
        self.assertNotIn('artifact": str(log_path.relative_to(ROOT))', SMOKE)
        self.assertIn('artifact": safe_artifact_path(log_path)', SMOKE)

    def test_run_debug_matrix_prioritizes_nonzero_exit_as_failed(self):
        nonzero_idx = MATRIX.index('if code != 0:')
        failed_idx = MATRIX.index('status = "failed"', nonzero_idx)
        skip_idx = MATRIX.index('elif _looks_like_full_skip(combined):')
        self.assertLess(nonzero_idx, skip_idx)
        self.assertLess(failed_idx, skip_idx)

    def test_skip_string_alone_does_not_override_failed(self):
        self.assertIn('SKIP: RUN_ATLAS_BACKEND_E2E is not set', SMOKE)
        self.assertIn('if code != 0:', MATRIX)
        self.assertNotIn('or "SKIP:" in combined', MATRIX)

    def test_timeout_remains_separate_and_final_status_detects_failures(self):
        self.assertIn('status = "timeout"', MATRIX)
        self.assertIn('payload["status"] = "finished_with_failures"', MATRIX)

    def test_debug_harness_safety_remains(self):
        self.assertNotIn('approve_plan', MATRIX)
        self.assertNotIn('execute_preview', MATRIX)
        self.assertNotIn('apply_patch', MATRIX)
        self.assertNotIn('shell=True', MATRIX)

    def test_wait_plan_and_approval_error_summaries_stay_short(self):
        self.assertIn('def compact_atlas_diag_reason', SMOKE)
        self.assertIn('artifact=atlas_lifecycle_final.json', SMOKE)
        self.assertNotIn('atlas wait-plan did not complete successfully: {json.dumps(diag', SMOKE)
        self.assertNotIn('approve button missing on completed state: {json.dumps', SMOKE)
        self.assertNotIn('open approval panel button missing in completed state: {json.dumps', SMOKE)


if __name__ == '__main__':
    unittest.main()
