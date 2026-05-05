import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / "ui.html").read_text(encoding="utf-8")
SMOKE = (ROOT / "scripts" / "smoke_ui_modes_playwright.py").read_text(encoding="utf-8")
MATRIX = (ROOT / "scripts" / "run_debug_test_matrix.py").read_text(encoding="utf-8")


class Phase312AtlasMobileUiCleanupContract(unittest.TestCase):
    def _atlas_block(self) -> str:
        return UI.split('<!-- ATLAS MODE -->', 1)[1].split('<div class="agent-col mob-hidden"', 1)[0]

    def _chat_block(self) -> str:
        return UI.split('<!-- CHAT -->', 1)[1].split('<!-- ATLAS MODE -->', 1)[0]

    def test_redundant_atlas_heading_and_explainer_removed(self):
        atlas = self._atlas_block()
        self.assertNotIn('<div class="agent-head"><h3>Atlas</h3></div>', atlas)
        self.assertNotIn('<div class="agent-head"><h3>Workflow Workbench</h3></div>', atlas)
        self.assertNotIn(
            'Workflow Workbench: Requirement / Plan / Review / Approval / Agent Execution / Execute Preview / Patch Review / Apply.',
            atlas,
        )

    def test_legacy_removed_from_normal_workbench_tabs(self):
        tabs = UI.split('<div class="atlas-subview-tabs"', 1)[1].split('</div>', 1)[0]
        self.assertIn("data-atlas-subview-tab=\"overview\"", tabs)
        self.assertIn("data-atlas-subview-tab=\"plan\"", tabs)
        self.assertIn("data-atlas-subview-tab=\"runs\"", tabs)
        self.assertIn("data-atlas-subview-tab=\"dashboard\"", tabs)
        self.assertIn("data-atlas-subview-tab=\"patch_review\"", tabs)
        self.assertNotIn("data-atlas-subview-tab=\"legacy\"", tabs)
        self.assertIn("const ATLAS_SUBVIEWS = ['overview', 'plan', 'runs', 'dashboard', 'patch_review'];", UI)

    def test_workbench_collapse_expand_and_compact_summary(self):
        atlas = self._atlas_block()
        self.assertIn('id="atlas-workbench-collapse-btn"', atlas)
        self.assertIn('onclick="toggleAtlasWorkbenchCollapse()"', atlas)
        self.assertIn('class="atlas-workbench-summary"', atlas)
        self.assertIn('Current:', atlas)
        self.assertIn('Last Run:', atlas)
        self.assertIn('Status:', atlas)
        self.assertIn('atlas-workbench-summary-label', UI)
        self.assertIn('display:flex;align-items:center;gap:6px;flex-wrap:wrap', UI)
        self.assertIn('function setAtlasWorkbenchCollapsed(collapsed)', UI)
        self.assertIn('#atlas-workbench-card.is-collapsed .atlas-workbench-body{display:none!important}', UI)

    def test_overview_owns_start_atlas_plan_is_view_only(self):
        overview = UI.split('data-atlas-subview-panel="overview"', 1)[1].split('data-atlas-subview-panel="plan"', 1)[0]
        plan = UI.split('data-atlas-subview-panel="plan"', 1)[1].split('data-atlas-subview-panel="runs"', 1)[0]
        self.assertIn('id="atlas-requirement-input"', overview)
        self.assertIn('onclick="startAtlasWorkflow()"', overview)
        self.assertIn('No plan yet', plan)
        self.assertNotIn('onclick="startAtlasWorkflow()"', plan)

    def test_mobile_width_overflow_guards(self):
        for token in [
            '*,*::before,*::after{box-sizing:border-box',
            'overflow-x:hidden;width:100%;max-width:100%',
            '.atlas-panel-col{overflow-y:auto;overflow-x:hidden',
            'min-width:0;max-width:100%',
            'width:calc(100% - 16px)!important',
            'max-width:100%;min-width:0;min-height:84px',
        ]:
            self.assertIn(token, UI)

    def test_chat_decoupled_from_planning_surface(self):
        chat = self._chat_block()
        for forbidden in [
            'phase1-plan-toggle',
            'phase1-plan-panel',
            'Plan設定',
            'Use Chat Input',
            'Atlas Plan mirror',
            'Atlas status mirror',
            'Open Atlas',
        ]:
            self.assertNotIn(forbidden, chat)
        self.assertNotIn('Chat is for lightweight conversation', chat)
        self.assertNotIn('dedicated workflow mode', chat)
        self.assertNotIn('id="chat-task-toggle"', chat)
        self.assertNotIn('Legacy Task', chat)

    def test_agent_execution_migration_marker(self):
        atlas = self._atlas_block()
        self.assertIn('id="atlas-agent-execution-marker"', atlas)
        self.assertIn('data-atlas-agent-execution="true"', atlas)
        self.assertNotIn('id="atlas-agent-execution-section"', atlas)
        self.assertNotIn('Agent execution is moving under Atlas', atlas)
        self.assertIn('Legacy Agent Advanced', UI)
        agent_panel = UI.split('<div class="agent-panel-col mob-hidden"', 1)[1].split('<!-- ECHO MODE', 1)[0]
        self.assertNotIn('onclick="startAtlasWorkflow()"', agent_panel)
        self.assertNotIn('Open Atlas Panel', agent_panel)

    def test_smoke_baseline_current_ui_and_legacy_informational(self):
        self.assertIn('async def verify_atlas_current_ui_smoke(page) -> None:', SMOKE)
        self.assertIn('("atlas_current_ui_smoke", verify_atlas_current_ui_smoke)', SMOKE)
        self.assertIn('TestPreset("atlas_current_ui_smoke"', MATRIX)
        self.assertIn('LEGACY_TEST_PRESETS', MATRIX)
        self.assertIn('legacy_ui_9of9_mock', MATRIX)
        self.assertNotIn('TestPreset("ui_9of9_mock"', MATRIX)
        default_list = MATRIX.split('TEST_PRESETS: list[TestPreset] = [', 1)[1].split(']\n\nLEGACY_TEST_PRESETS', 1)[0]
        self.assertNotIn('ui_9of9_mock', default_list)
        self.assertNotIn('legacy_ui_9of9_mock', default_list)


    def test_debug_harness_separates_default_and_legacy_ui_presets(self):
        self.assertIn('from scripts.run_debug_test_matrix import LEGACY_TEST_PRESETS, TEST_PRESETS', (ROOT / 'main.py').read_text(encoding='utf-8'))
        self.assertIn('Default acceptance presets', (ROOT / 'main.py').read_text(encoding='utf-8'))
        self.assertIn('Legacy / manual informational presets', (ROOT / 'main.py').read_text(encoding='utf-8'))
        self.assertIn('not run by Run All Tests', (ROOT / 'main.py').read_text(encoding='utf-8'))
        self.assertIn('for preset in TEST_PRESETS:', MATRIX)
        self.assertNotIn('for preset in TEST_PRESETS + LEGACY_TEST_PRESETS', MATRIX)
        self.assertIn('| id | status | exit | duration | error summary | artifact path | logs |', MATRIX)
        self.assertIn('stdout_log_path', MATRIX)

    def test_safety_no_destructive_presets_or_auto_actions(self):
        combined = SMOKE + MATRIX
        for forbidden in ['approve_plan preset', 'execute_preview preset', 'apply_patch preset', 'auto approve', 'auto apply']:
            self.assertNotIn(forbidden, combined.lower())
        guided = SMOKE.split('async def verify_atlas_guided_workflow_safe_journey(page) -> None:', 1)[1].split('\n\n\ndef _truncate_json', 1)[0]
        self.assertNotIn('Open Approval Panel")\n  if await approval_btn.count()', guided)
        self.assertNotIn('Open Execute Preview")\n  if await execute_btn.count()', guided)
        self.assertNotIn('Apply Patch', guided)


if __name__ == '__main__':
    unittest.main()
