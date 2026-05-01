from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.plan_approval_manager import PlanApprovalManager
from agent.plan_review_schema import PlanReviewResult
from agent.plan_schema import ImplementationStep, Plan
from agent.plan_storage import PlanStorage


class Phase5PlanApprovalTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.storage = PlanStorage(Path(self.td.name) / "ca_data")
        self.manager = PlanApprovalManager(self.storage)

    def tearDown(self):
        self.td.cleanup()

    def _plan(self, status: str = "planned", destructive: bool = False) -> Plan:
        return Plan(
            plan_id="plan_phase5",
            requirement_id="req_phase5",
            user_goal="goal",
            requirement_summary="summary",
            implementation_steps=[ImplementationStep(step_id="s1", title="t1")],
            status=status,
            destructive_change_detected=destructive,
        )

    def _review(self, risk: str = "low", next_action: str = "proceed", requires_confirm: bool = False) -> PlanReviewResult:
        return PlanReviewResult(
            review_id="review_phase5",
            plan_id="plan_phase5",
            requirement_id="req_phase5",
            overall_risk=risk,
            recommended_next_action=next_action,
            requires_user_confirmation=requires_confirm,
            destructive_change_detected=requires_confirm,
        )

    def _save(self, plan: Plan, review: PlanReviewResult):
        self.storage.save_plan(plan, user_input="input", interpreted_goal="goal", review_result=review)

    def test_low_risk_approve(self):
        self._save(self._plan(), self._review(risk="low"))
        out = self.manager.decide(plan_id="plan_phase5", decision="approve", user_comment="確認OK")
        self.assertEqual(out["approval"]["status"], "approved")
        self.assertTrue(out["approval"]["execution_ready"])
        self.assertEqual(out["plan"]["status"], "execution_ready")

    def test_high_risk_approve_without_ack_fails(self):
        self._save(self._plan(), self._review(risk="high", requires_confirm=True))
        with self.assertRaises(ValueError):
            self.manager.decide(plan_id="plan_phase5", decision="approve")
        self.assertEqual(self.storage.load_plan("plan_phase5")["status"], "planned")

    def test_high_risk_approve_with_ack_succeeds(self):
        self._save(self._plan(), self._review(risk="high", requires_confirm=True))
        out = self.manager.decide(plan_id="plan_phase5", decision="approve", risk_acknowledged=True)
        self.assertTrue(out["approval"]["execution_ready"])

    def test_destructive_without_ack_fails(self):
        plan = self._plan(destructive=True)
        self._save(plan, self._review(risk="high", requires_confirm=True))
        with self.assertRaises(ValueError):
            self.manager.decide(plan_id="plan_phase5", decision="approve", risk_acknowledged=True)

    def test_destructive_with_ack_succeeds(self):
        plan = self._plan(destructive=True)
        self._save(plan, self._review(risk="high", requires_confirm=True))
        out = self.manager.decide(
            plan_id="plan_phase5", decision="approve", risk_acknowledged=True, destructive_change_acknowledged=True
        )
        self.assertEqual(out["plan"]["status"], "execution_ready")

    def test_request_revision(self):
        self._save(self._plan(), self._review())
        out = self.manager.decide(plan_id="plan_phase5", decision="request_revision", revision_request="Dockerは除外")
        self.assertEqual(out["approval"]["status"], "revision_requested")
        self.assertEqual(out["plan"]["status"], "revision_requested")

    def test_reject(self):
        self._save(self._plan(), self._review())
        out = self.manager.decide(plan_id="plan_phase5", decision="reject", user_comment="範囲過大")
        self.assertEqual(out["approval"]["status"], "rejected")
        self.assertEqual(out["plan"]["status"], "rejected")

    def test_rejected_plan_cannot_approve(self):
        self._save(self._plan(status="rejected"), self._review())
        with self.assertRaises(ValueError):
            self.manager.decide(plan_id="plan_phase5", decision="approve")

    def test_storage_save_load_find_latest_and_japanese(self):
        self._save(self._plan(), self._review())
        out = self.manager.decide(
            plan_id="plan_phase5", decision="request_revision", revision_request="依存関係変更を分離", user_comment="日本語コメント"
        )
        approval_id = out["approval_id"]
        loaded = self.storage.load_approval(approval_id)
        self.assertEqual(loaded["user_comment"], "日本語コメント")
        latest = self.storage.find_latest_approval_for_plan("plan_phase5")
        self.assertIsNotNone(latest)
        md = self.storage.approval_markdown_path(approval_id).read_text(encoding="utf-8")
        self.assertIn("依存関係変更を分離", md)

    def test_no_implementation_executed_message(self):
        self._save(self._plan(), self._review())
        out = self.manager.decide(plan_id="plan_phase5", decision="approve")
        self.assertIn("No implementation was executed", out["message"])


if __name__ == "__main__":
    unittest.main()
