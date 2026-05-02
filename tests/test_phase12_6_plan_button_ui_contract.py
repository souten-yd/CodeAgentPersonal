from __future__ import annotations

import unittest
from pathlib import Path


class Phase12_6PlanButtonUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = Path('ui.html').read_text(encoding='utf-8')

    def test_plan_button_calls_new_e2e_function(self):
        self.assertIn('onclick="startPlanWorkflow()"', self.ui)
        self.assertIn('Start Atlas', self.ui)

    def test_plan_workflow_status_panel_exists(self):
        self.assertIn('Atlas Workflow Status', self.ui)
        self.assertIn('function _renderPlanWorkflowStatusPanel()', self.ui)

    def test_execute_preview_controls_exist(self):
        self.assertIn('Execute Preview (dry_run)', self.ui)
        self.assertIn('Execute Preview (safe_apply)', self.ui)

    def test_patch_generation_mode_and_preview_flags_exist(self):
        self.assertIn('id="${cardId}-patch-mode"', self.ui)
        self.assertIn('id="${cardId}-preview-only" checked', self.ui)
        self.assertIn('id="${cardId}-apply-patches" checked', self.ui)

    def test_patch_review_refresh_and_dashboard_fallback_exist(self):
        self.assertIn('await loadPhase8Patches(cid, res.run_id);', self.ui)
        self.assertIn('/api/runs/${encodeURIComponent(runId)}/patch-dashboard', self.ui)
        self.assertIn('Dashboard not available yet', self.ui)


if __name__ == '__main__':
    unittest.main()
