import importlib.util
import sys
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'main.py').read_text(encoding='utf-8')
MATRIX = (ROOT / 'scripts' / 'run_debug_test_matrix.py').read_text(encoding='utf-8')
SMOKE = (ROOT / 'scripts' / 'smoke_ui_modes_playwright.py').read_text(encoding='utf-8')


def _load_module(path: Path, name: str):
    scripts_dir = str((ROOT / "scripts").resolve())
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestPhase300DebugTestHarnessContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke_module = _load_module(ROOT / 'scripts' / 'smoke_ui_modes_playwright.py', 'smoke_ui_modes_playwright_contract')

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

    def test_smoke_scenario_metadata_and_resolution(self):
        smoke = self.smoke_module
        self.assertIn('atlas_plan_api_contract', smoke.SMOKE_SCENARIOS)
        spec = smoke.SMOKE_SCENARIOS['atlas_plan_api_contract']
        self.assertEqual(spec.kind, 'backend_api')
        self.assertTrue(spec.allowed_in_preflight_only)
        resolved = smoke.resolve_smoke_scenarios(
            only=['atlas_plan_api_contract'],
            preflight_only_mode=True,
            run_backend_e2e=False,
            run_wait_plan=False,
            run_resolve_clarification=False,
            run_check_plan_approval=False,
            run_check_plan_approval_actionable=False,
        )
        self.assertIn('atlas_plan_api_contract', resolved)
        self.assertNotEqual(resolved, [])

    def test_matrix_presets_match_smoke_registry(self):
        smoke = self.smoke_module
        registry = set(smoke.SMOKE_SCENARIOS.keys())
        self.assertIn('_validate_smoke_only_presets', MATRIX)
        for val in re.findall(r'"PLAYWRIGHT_SMOKE_ONLY":\s*"([^"]+)"', MATRIX):
            self.assertIn(val, registry)


if __name__ == '__main__':
    unittest.main()
